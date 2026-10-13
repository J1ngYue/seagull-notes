// DOM regression without a browser: node tests/notebook_pagination.cjs <jsdom module path>
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {JSDOM} = require(process.argv[2] || 'jsdom');
const dom = new JSDOM('<style>.book-page{padding:20px}</style><div id="spread"></div><section id="source"><header><h2>Topic</h2></header><div class="prose"><p>Before table.</p><table><thead><tr><th>Column</th></tr></thead><tbody><tr><td>Table row.</td></tr></tbody></table><p>After table.</p><ol><li>First step.</li><li>Second step.</li></ol><p>After list.</p></div></section>', {runScripts:'outside-only'});
const {window} = dom;
window.matchMedia = () => ({matches:false});
Object.defineProperties(window.HTMLElement.prototype, {
  clientWidth:{get:()=>1000}, clientHeight:{get:()=>1000}, scrollHeight:{get:()=>200}
});
window.eval(fs.readFileSync(path.join(__dirname,'../skill/assets/book-pagination.js'),'utf8'));
const source=window.document.querySelector('#source'),prose=source.querySelector('.prose');
const originalHTML=prose.innerHTML,originalNodes=Array.from(prose.children);
const pagination=window.paginateNotebookBook(window.document.querySelector('#spread'),[{chapter:0,header:source.querySelector('header'),sources:[prose]}],{bindMath() {},reflow() {}});
const rendered=Array.from(pagination.pages[0].querySelectorAll('.prose p,.prose tbody>tr,.prose li')).map(node=>node.textContent);
assert.deepEqual(rendered,['Before table.','Table row.','After table.','First step.','Second step.','After list.']);
pagination.restore();
assert.equal(prose.innerHTML,originalHTML);
assert.ok(originalNodes.every((node,index)=>node===prose.children[index]));
dom.window.close();
process.stdout.write('Pagination preserves paragraph, table and list order and restores original nodes.\n');
