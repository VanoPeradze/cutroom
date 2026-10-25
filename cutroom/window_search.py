"""Default-off, durable numeric discovery. A page/ACK confers no edit authority.

The local run record, not a caller's cursor, owns the cumulative budget. Locks
are fail-fast and never stolen. An uncertain crash fails closed (inflight), not
restarted with a fresh budget. This is not a general untrusted storage service.
"""
from __future__ import annotations

from bisect import bisect_right
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
import hashlib
import hmac
import json
import math
import os
from pathlib import Path
import re
import secrets
import time
from typing import Callable

from .edit_windows import EditWindowError, _identity
from .window_retrieval import EPSILON, retrieve_windows, RECOVERY_ENTRY_POLICY

SEARCH_POLICY = 'durable-round-robin-ordered-paths-v1'
MAX_CHECKPOINT_BYTES = 65536


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf8')


@dataclass(frozen=True)
class SearchBudget:
    total_expansions: int = 4096
    batch_expansions: int = 256
    page_candidates: int = 64
    active_seconds: float = 10.

    def __post_init__(self):
        for key, upper in [('total_expansions',4096),('batch_expansions',256),('page_candidates',64)]:
            if type(getattr(self,key)) is not int or not 1 <= getattr(self,key) <= upper:
                raise EditWindowError('Invalid cumulative search budget: '+key)
        if (isinstance(self.active_seconds,bool) or not isinstance(self.active_seconds,(int,float))
                or not math.isfinite(self.active_seconds) or not 0 < self.active_seconds <= 10.):
            raise EditWindowError('Invalid cumulative search time budget')


class SearchStore:
    """Explicit internal local directory. MAC detects edits, not hostile owner access."""
    def __init__(self, directory):
        self.directory = Path(directory)

    @contextmanager
    def locked(self, run_id):
        if not isinstance(run_id,str) or not re.fullmatch('[0-9a-f]{32}',run_id):
            raise EditWindowError('Invalid search run ID')
        self.directory.mkdir(parents=True,exist_ok=True)
        lock = self.directory/(run_id+'.lock')
        try:
            fd = os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
        except FileExistsError as exc:
            raise EditWindowError('Search run busy or interrupted; lock is never stolen') from exc
        os.close(fd)
        try:
            yield self.directory/(run_id+'.json')
        finally:
            lock.unlink()

    def key(self):
        path=self.directory/'.integrity-key'
        try:
            fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
        except FileExistsError:
            key=path.read_bytes()
        else:
            key=secrets.token_bytes(32)
            with os.fdopen(fd,'wb') as out:
                out.write(key);out.flush();os.fsync(out.fileno())
        if len(key)!=32: raise EditWindowError('Invalid search integrity key')
        return key

    def read(self,path):
        if path.stat().st_size>MAX_CHECKPOINT_BYTES: raise EditWindowError('Oversized search checkpoint')
        def pairs(items):
            obj={}
            for k,v in items:
                if k in obj: raise EditWindowError('Duplicate checkpoint field')
                obj[k]=v
            return obj
        try:
            record=json.loads(path.read_text('utf8'),object_pairs_hook=pairs,
                              parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite')))
            signature=record.pop('mac')
            if not hmac.compare_digest(signature,hmac.new(self.key(),_json(record),hashlib.sha256).hexdigest()):
                raise ValueError('integrity')
            if record['inflight']: raise EditWindowError('Uncertain interrupted search batch; no automatic restart')
            return record
        except (KeyError,TypeError,ValueError,json.JSONDecodeError) as exc:
            raise EditWindowError('Invalid or uncertain search checkpoint: '+str(exc)) from exc

    def write(self,path,record):
        envelope={**record,'mac':hmac.new(self.key(),_json(record),hashlib.sha256).hexdigest()}
        data=_json(envelope)
        if len(data)>MAX_CHECKPOINT_BYTES: raise EditWindowError('Search checkpoint size exceeded')
        temporary=path.with_suffix('.tmp')
        with temporary.open('wb') as out:
            out.write(data);out.flush();os.fsync(out.fileno())
        os.replace(temporary,path)


@dataclass(frozen=True)
class ResumableSearchRequest:
    store: SearchStore = field(repr=False,compare=False)
    run_id: str = field(default_factory=lambda:secrets.token_hex(16))
    revision: int = 0
    ack_page: str | None = None
    budget: SearchBudget = field(default_factory=SearchBudget)

    def __post_init__(self):
        if (not isinstance(self.store,SearchStore) or not isinstance(self.budget,SearchBudget)
                or not isinstance(self.run_id,str) or not re.fullmatch('[0-9a-f]{32}',self.run_id)
                or type(self.revision) is not int or self.revision<0
                or (self.ack_page is not None and (not isinstance(self.ack_page,str)
                    or not re.fullmatch('[0-9a-f]{64}',self.ack_page)))):
            raise EditWindowError('Invalid resumable search request')


def discover_page(source,bounds,policy,request,identity,cancel_check=None,*,units=None,
                  no_cuts=False,clock:Callable[[],float]=time.perf_counter):
    """One bounded numeric page. Replays return the pending page, never rewind.

    Index construction is bounded separately by existing source/window caps and
    charged to active time on each NEW batch. Idempotent replay does revalidate
    input/index identity; that validation overhead is not search expansion work.
    """
    if request.budget.total_expansions>policy.max_transitions:
        raise EditWindowError('Resumable search cannot raise the existing total transition cap')
    started=clock()
    args={'units':units} if policy.windows.speech_units else {}
    continuous=retrieve_windows(source,bounds,policy.windows,cancel_check,**args)
    component=retrieve_windows(source,{**bounds,'minimum_seconds':0.,'origin':'resumable_component_index'},
                               policy.windows,cancel_check,**args)
    parts=component.candidates; singles=continuous.candidates; rows=source.rows
    continuous_set={(c.first,c.last) for c in singles}
    root_groups=[]
    for i,c in enumerate(parts):
        if not root_groups or parts[root_groups[-1][0]].first!=c.first:root_groups.append([i,i+1])
        else:root_groups[-1][1]=i+1
    if len(root_groups)>128:
        raise EditWindowError('Resumable frontier supports at most 128 indexed root entries')
    firsts=[c.first for c in parts];times=[rows[c.first].start for c in parts]
    policy_record=asdict(policy)
    # Keep pre-existing speech_units=False in durable legacy bindings.
    if policy_record['windows'].pop('defer_recovery_only_starts'):
        policy_record['windows']['defer_recovery_only_starts']=True
        policy_record['windows']['recovery_entry_policy']=RECOVERY_ENTRY_POLICY
    binding=_identity('resumable-search-input',[SEARCH_POLICY,identity,source.fingerprint,bounds,
                    continuous.fingerprint,component.fingerprint,policy_record,asdict(request.budget),no_cuts,
                    units.fingerprint if units else None])
    token=[request.revision,request.ack_page]
    with request.store.locked(request.run_id) as path:
        created=path.with_suffix('.created')
        if path.exists():
            if not created.exists():raise EditWindowError('Missing authoritative run creation marker')
            record=request.store.read(path)
            if record['identity']!=binding:raise EditWindowError('Stale or incompatible search identity')
            if record['last_request']==token:
                return record['page']
            if record['revision']!=request.revision:raise EditWindowError('Stale search revision; refusing budget rewind')
            if not record['page'] or request.ack_page!=record['page']['page_id']:
                raise EditWindowError('Exact pending page ACK is required')
            if record['page']['indexed_domain_exhausted'] or record['page']['budget_exhausted']:
                return record['page']  # terminal ACK cannot create a new budget/page
        else:
            if request.revision!=0 or request.ack_page is not None:
                raise EditWindowError('Missing search run; no automatic restart')
            try:
                marker=os.open(created,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
            except FileExistsError as exc:
                raise EditWindowError('Missing previously created search run; no budget reset') from exc
            with os.fdopen(marker,'wb') as out:
                out.write(binding.encode('ascii'));out.flush();os.fsync(out.fileno())
            record={'identity':binding,'revision':0,'inflight':False,'last_request':None,'page':None,
                    'state':{'continuous':0,'turn':0,'roots':[
                        {'next':a,'end':b,'stack':[]} for a,b in root_groups],
                        'expansions':0,'active_seconds':0.,'roots_visited':[]}}
        state=record['state'];budget=request.budget
        record['inflight']=True
        request.store.write(path,record)  # uncertainty after this point must never reset work
        page=[];work=0;cancelled=None
        def timed_out():return state['active_seconds']+max(0.,clock()-started)>=budget.active_seconds
        def unfinished():
            return state['continuous']<len(singles) or (not no_cuts and policy.max_ranges>1 and
                any(r['next']<r['end'] or r['stack'] for r in state['roots']))
        def successor_after(last):
            return max(bisect_right(firsts,last+1),bisect_right(times,rows[last].end))
        try:
            while (work<budget.batch_expansions and len(page)<budget.page_candidates
                   and state['expansions']<budget.total_expansions and not timed_out() and unfinished()):
                if cancel_check:cancel_check()
                # Continuous outputs and root exploration take alternating work
                # turns, preventing a dense continuous table starving all cuts.
                active=[i for i,r in enumerate(state['roots']) if r['next']<r['end'] or r['stack']]
                use_single=state['continuous']<len(singles) and (
                    no_cuts or policy.max_ranges==1 or not active or state['expansions']%2==0)
                work+=1;state['expansions']+=1
                if use_single:
                    c=singles[state['continuous']];state['continuous']+=1
                    page.append({'ranges':[[c.first,c.last]],'duration':c.duration})
                    continue
                selected=next((i for offset in range(len(root_groups))
                    if (i:=(state['turn']+offset)%len(root_groups)) in active),None)
                r=state['roots'][selected];state['turn']=(selected+1)%len(root_groups)
                if selected not in state['roots_visited']:state['roots_visited'].append(selected)
                if not r['stack']:
                    ci=r['next'];r['next']+=1;c=parts[ci]
                    r['stack']=[[ci,successor_after(c.last)]]
                    if bounds['minimum_seconds']-EPSILON<=c.duration<=bounds['maximum_seconds']+EPSILON and (c.first,c.last) not in continuous_set:
                        page.append({'ranges':[[c.first,c.last]],'duration':c.duration})
                    if len(r['stack'])>=policy.max_ranges:r['stack'].pop()
                    continue
                stack=r['stack'];next_i=stack[-1][1]
                if next_i>=len(parts):stack.pop();continue
                stack[-1][1]+=1  # rejected edges also consume budget and retain the next edge
                chosen=[parts[f[0]] for f in stack];c=parts[next_i]
                total=sum(p.duration for p in chosen)+c.duration
                if (c.first<=chosen[-1].last+1 or rows[c.first].start<=rows[chosen[-1].last].end
                    or rows[c.last].end-rows[chosen[0].first].start>policy.max_source_span
                    or total>bounds['maximum_seconds']+EPSILON):continue
                ranges=[[p.first,p.last] for p in chosen]+[[c.first,c.last]]
                if total>=bounds['minimum_seconds']-EPSILON:page.append({'ranges':ranges,'duration':total})
                if len(stack)+1<policy.max_ranges:stack.append([next_i,successor_after(c.last)])
        except BaseException as exc:
            from .jobs import JobCancelled
            if not isinstance(exc,(InterruptedError,JobCancelled)):raise
            cancelled=exc
        state['active_seconds']+=max(0.,clock()-started)
        exhausted=not unfinished()
        budget_hit=state['expansions']>=budget.total_expansions or state['active_seconds']>=budget.active_seconds
        record['revision']+=1
        page_id=hashlib.sha256(_json([binding,record['revision'],state,page])).hexdigest()
        receipt={'run_id':request.run_id,'revision':record['revision'],'page_id':page_id,
                 'candidates':page,'batch_expansions':work,'total_expansions':state['expansions'],
                 'active_seconds':state['active_seconds'],'indexed_roots':len(root_groups),
                 'visited_roots':len(state['roots_visited']),
                 'frontier_roots':sum(bool(r['next']<r['end'] or r['stack']) for r in state['roots']) if not no_cuts and policy.max_ranges>1 else 0,
                 'pending_continuous':len(singles)-state['continuous'],
                 'search_status':'cancelled' if cancelled else 'indexed_domain_exhausted' if exhausted else
                    'total_budget_exhausted_incomplete' if budget_hit else 'batch_incomplete',
                 'indexed_domain_exhausted':exhausted,'budget_exhausted':budget_hit,
                 'component_index_complete':len(parts)==component.feasible_pairs,
                 'continuous_index_complete':len(singles)==continuous.feasible_pairs,
                 'all_legal_edits_exhausted':False,'semantic_assessment':'not_performed',
                 'policy':SEARCH_POLICY,'budget':asdict(budget),
                 'memory_bounds':{'checkpoint_bytes':MAX_CHECKPOINT_BYTES,'component_records':2048,
                    'continuous_records':2048,'root_frontiers':128,'stack_depth':3,'page_candidates':64,
                    'materialized_row_references':policy.windows.max_view_row_references,
                    'materialized_text_characters':policy.windows.max_view_text_characters},
                 'time_budget_scope':'cumulative_discovery_and_index_preparation_not_whole_plan_edit',
                 'time_deadline':'checked_between_edges_atomic_step_and_commit_may_overrun',
                 'validation_replay_cost':'bounded_index_identity_validation_not_discovery_work'}
        record.update(page=receipt,inflight=False,last_request=token)
        request.store.write(path,record)
        if cancelled:raise cancelled
        return receipt
