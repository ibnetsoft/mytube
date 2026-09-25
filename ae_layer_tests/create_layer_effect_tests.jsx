var psdPath = "D:/Projects/에어스튜디오/mytube_clone_20260828/ae_layer_tests/source.psd";
var projectPath = "D:/Projects/에어스튜디오/mytube_clone_20260828/ae_layer_tests/layer_effect_tests.aep";
var reportPath = "D:/Projects/에어스튜디오/mytube_clone_20260828/ae_layer_tests/effect_test_report.txt";
var outDir = "D:/Projects/에어스튜디오/mytube_clone_20260828/ae_layer_tests/";

var W = 540;
var H = 960;
var FPS = 24;
var DUR = 3;
var START_Y = 5200;

function logLine(lines, text) {
  lines.push(text);
}

function writeReport(lines) {
  var out = new File(reportPath);
  out.encoding = "UTF-8";
  out.open("w");
  for (var i = 0; i < lines.length; i++) {
    out.writeln(lines[i]);
  }
  out.close();
}

function importPsdAsComp() {
  var psd = new File(psdPath);
  var options = new ImportOptions(psd);
  options.importAs = ImportAsType.COMP_CROPPED_LAYERS;
  return app.project.importFile(options);
}

function compPosForDocY(docY, scalePercent) {
  return (27000 * scalePercent / 100) / 2 - docY * scalePercent / 100;
}

function addSourceLayers(targetComp, sourceComp, scalePercent, docY, stagger, parallaxAmount) {
  var added = [];
  for (var i = sourceComp.numLayers; i >= 1; i--) {
    var srcLayer = sourceComp.layer(i);
    if (!srcLayer.source) {
      continue;
    }
    var layer = targetComp.layers.add(srcLayer.source);
    layer.name = srcLayer.name;
    layer.property("Scale").setValue([scalePercent, scalePercent]);
    var yOffset = parallaxAmount * (sourceComp.numLayers - i);
    layer.property("Position").setValue([W / 2, compPosForDocY(docY + yOffset, scalePercent)]);
    layer.startTime = stagger ? (sourceComp.numLayers - i) * 0.04 : 0;
    layer.outPoint = DUR;
    added.push(layer);
  }
  return added;
}

function addTintFlash(comp, opacity1, opacity2) {
  var solid = comp.layers.addSolid([1, 1, 1], "flash_overlay", W, H, 1, DUR);
  solid.blendingMode = BlendingMode.ADD;
  solid.property("Opacity").setValueAtTime(0, opacity1);
  solid.property("Opacity").setValueAtTime(0.15, opacity2);
  solid.property("Opacity").setValueAtTime(0.45, 0);
  return solid;
}

function tryAddEffect(layer, matchName, label, lines) {
  try {
    var fx = layer.property("Effects").addProperty(matchName);
    logLine(lines, "effect_added=" + label + " on " + layer.name);
    return fx;
  } catch (err) {
    logLine(lines, "effect_failed=" + label + " on " + layer.name + " / " + err.toString());
    return null;
  }
}

var lines = [];
app.beginSuppressDialogs();

try {
  if (app.project) {
    app.project.close(CloseOptions.DO_NOT_SAVE_CHANGES);
  }
  app.newProject();

  var sourceComp = importPsdAsComp();
  var baseScale = W / sourceComp.width * 100;
  logLine(lines, "source_comp=" + sourceComp.name + " " + sourceComp.width + "x" + sourceComp.height + " layers=" + sourceComp.numLayers);
  logLine(lines, "test_scale_percent=" + baseScale);

  var scroll = app.project.items.addComp("test_01_scroll_pan", W, H, 1, DUR, FPS);
  var scrollLayer = scroll.layers.add(sourceComp);
  scrollLayer.name = "full_psd_scroll";
  scrollLayer.property("Scale").setValue([baseScale, baseScale]);
  scrollLayer.property("Position").setValueAtTime(0, [W / 2, compPosForDocY(START_Y, baseScale)]);
  scrollLayer.property("Position").setValueAtTime(DUR, [W / 2, compPosForDocY(START_Y + 1450, baseScale)]);
  scrollLayer.property("Scale").setValueAtTime(0, [baseScale, baseScale]);
  scrollLayer.property("Scale").setValueAtTime(DUR, [baseScale * 1.04, baseScale * 1.04]);
  app.project.renderQueue.items.add(scroll).outputModule(1).file = new File(outDir + "test_01_scroll_pan.avi");
  logLine(lines, "queued=test_01_scroll_pan.avi");

  var parallax = app.project.items.addComp("test_02_layer_parallax", W, H, 1, DUR, FPS);
  var layers = addSourceLayers(parallax, sourceComp, baseScale, START_Y + 300, true, 65);
  for (var p = 0; p < layers.length; p++) {
    var l = layers[p];
    var pos = l.property("Position").value;
    var depthShift = (p - 1.5) * 24;
    l.property("Position").setValueAtTime(0, [pos[0] - depthShift, pos[1]]);
    l.property("Position").setValueAtTime(DUR, [pos[0] + depthShift, pos[1] - 70 - p * 10]);
    var s = l.property("Scale").value;
    l.property("Scale").setValueAtTime(0, s);
    l.property("Scale").setValueAtTime(DUR, [s[0] * (1.03 + p * 0.01), s[1] * (1.03 + p * 0.01)]);
  }
  app.project.renderQueue.items.add(parallax).outputModule(1).file = new File(outDir + "test_02_layer_parallax.avi");
  logLine(lines, "queued=test_02_layer_parallax.avi");

  var impact = app.project.items.addComp("test_03_shake_flash_glow", W, H, 1, DUR, FPS);
  var impactLayers = addSourceLayers(impact, sourceComp, baseScale * 1.02, START_Y + 650, false, 0);
  for (var q = 0; q < impactLayers.length; q++) {
    var il = impactLayers[q];
    var ip = il.property("Position").value;
    il.property("Position").setValueAtTime(0, [ip[0], ip[1]]);
    il.property("Position").setValueAtTime(0.12, [ip[0] - 18 + q * 8, ip[1] + 10]);
    il.property("Position").setValueAtTime(0.24, [ip[0] + 14 - q * 6, ip[1] - 8]);
    il.property("Position").setValueAtTime(0.42, [ip[0], ip[1]]);
    il.property("Position").setValueAtTime(DUR, [ip[0], ip[1] - 90]);
  }
  if (impactLayers.length > 0) {
    tryAddEffect(impactLayers[impactLayers.length - 1], "ADBE Glo2", "Glow", lines);
  }
  addTintFlash(impact, 75, 18);
  app.project.renderQueue.items.add(impact).outputModule(1).file = new File(outDir + "test_03_shake_flash_glow.avi");
  logLine(lines, "queued=test_03_shake_flash_glow.avi");

  app.project.save(new File(projectPath));
  logLine(lines, "project_saved=" + projectPath);
} catch (err) {
  logLine(lines, "ERROR=" + err.toString());
} finally {
  writeReport(lines);
  app.endSuppressDialogs(false);
}
