const test = require('node:test'), assert = require('node:assert/strict'), fs = require('node:fs'), ts = require('typescript')
const library = {}
new Function('exports', ts.transpileModule(fs.readFileSync(require.resolve('../lib/stdTemplateOverlay.ts'), 'utf8'), {
    compilerOptions: { module: 1, target: 9 },
}).outputText)(library)

test('explicit template background choices survive saving, while legacy text presets stay transparent', async () => {
    const settings = { std_image_template_enabled: true, std_template_text_layers: [], std_image_template_bg_url: '/background.png', std_image_template_bg_color: '#123456', std_template_shape_layers: [{ color: 'red' }] }
    const legacy = await library.templateOverlaySettings(settings)
    assert.equal(legacy.std_image_template_bg_url, null)
    assert.equal(legacy.std_image_template_bg_color, 'transparent')
    const explicit = await library.templateOverlaySettings({ ...settings, std_image_template_bg_transparent: false })
    assert.equal(explicit.std_image_template_bg_url, '/background.png')
    assert.equal(explicit.std_image_template_bg_color, '#123456')
    assert.deepEqual(explicit.std_template_shape_layers, settings.std_template_shape_layers)
})
