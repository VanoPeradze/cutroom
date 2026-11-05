// Test-only CDP boundary: selectors are argument data, never JavaScript source.
function readBrowserElementBox(selector) {
  const document = this.document;
  const element = document.querySelector(selector);
  if (!element || element.disabled || element.closest('[inert]')) {
    throw Error('Unavailable or inert UI control');
  }
  element.scrollIntoView({block: 'center'});
  const rect = element.getBoundingClientRect();
  if (!rect.width || !rect.height) throw Error('Hidden UI control');
  const hit = document.elementFromPoint(rect.x + rect.width / 2, rect.y + rect.height / 2);
  if (!hit || !(hit === element || element.contains(hit))) throw Error('UI control is covered');
  return {x: rect.x, y: rect.y, width: rect.width, height: rect.height};
}

async function browserElementBox(cdp, selector) {
  const root = await cdp.send('Runtime.evaluate', {expression: 'globalThis', returnByValue: false});
  if (root.exceptionDetails) throw Error(JSON.stringify(root.exceptionDetails));
  const objectId = root.result?.objectId;
  if (!objectId) throw Error('Browser global object unavailable');
  try {
    const result = await cdp.send('Runtime.callFunctionOn', {
      objectId,
      functionDeclaration: readBrowserElementBox.toString(),
      arguments: [{value: selector}],
      returnByValue: true,
      awaitPromise: true,
    });
    if (result.exceptionDetails) throw Error(JSON.stringify(result.exceptionDetails));
    return result.result.value;
  } finally {
    await cdp.send('Runtime.releaseObject', {objectId}).catch(() => {});
  }
}

module.exports = {browserElementBox, readBrowserElementBox};
