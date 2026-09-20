import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const html = readFileSync(new URL('./public/index.html', import.meta.url), 'utf8');
const repository = 'https://github.com/VanoPeradze/cutroom';

function region(tag, id) {
  const selector = id ? `[^>]*\\bid=["']${id}["']` : '';
  const match = html.match(new RegExp(`<${tag}\\b${selector}[^>]*>([\\s\\S]*?)</${tag}>`, 'i'));
  assert.ok(match, `Missing ${id ? `#${id}` : tag} region`);
  return match[1];
}

function linksTo(markup, url) {
  return [...markup.matchAll(/<a\b([^>]*)>([\s\S]*?)<\/a>/gi)]
    .filter(link => link[1].match(/\bhref=["']([^"']+)["']/i)?.[1] === url);
}

function assertLocalized(link) {
  assert.match(link[0], /\bdata-he=["'][^"']*[\u0590-\u05ff][^"']*["']/);
  assert.match(link[2].replace(/<[^>]+>/g, ''), /[A-Za-z]/, 'The default link text must be English');
}

test('repository links appear in navigation, download section, and footer', () => {
  assert.equal(linksTo(html, repository).length, 3);
  for (const markup of [region('nav'), region('section', 'download'), region('footer')]) {
    assert.equal(linksTo(markup, repository).length, 1);
  }
  assertLocalized(linksTo(region('section', 'download'), repository)[0]);
});

test('the FAQ offers a localized GitHub issue link', () => {
  const links = linksTo(region('section', 'help'), `${repository}/issues/new/choose`);
  assert.equal(links.length, 1);
  assertLocalized(links[0]);
});

test('language switching cannot replace links with plain text', () => {
  // site.js replaces each data-he element's contents with textContent in Hebrew.
  for (const element of html.matchAll(/<([a-z][\w-]*)\b([^>]*\bdata-he=["'][^"']*["'][^>]*)>([\s\S]*?)<\/\1>/gi)) {
    assert.doesNotMatch(element[3], /<a\b/i, 'Put data-he on the link or its text, not an ancestor');
  }
});

test('public website copy does not describe the repository as private', () => {
  assert.doesNotMatch(html, /private (?:GitHub )?(?:repository|repo)\b|\b(?:repository|repo) (?:is|remains) private|מאגר פרטי|המאגר (?:פרטי|נשאר פרטי)/i);
});
