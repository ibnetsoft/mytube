const fs = require('node:fs'), path = require('node:path'), ts = require('typescript')
const cache = new Map()
module.exports = function load(file) {
  file = path.resolve(file)
  if (cache.has(file)) return cache.get(file)
  const exports = {}; cache.set(file, exports)
  const source = ts.transpileModule(fs.readFileSync(file, 'utf8'), {compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText
  new Function('exports','require',source)(exports, name => name.startsWith('.')
    ? module.exports(path.resolve(path.dirname(file),name+'.ts')) : require(name))
  return exports
}
