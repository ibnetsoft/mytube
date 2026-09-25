var imagePath = "D:/Projects/에어스튜디오/mytube_clone_20260828/ae_wuxia_fx/sword_ruins.jpg";
var projectPath = "D:/Projects/에어스튜디오/mytube_clone_20260828/ae_wuxia_fx/wuxia_ae_fx.aep";
var renderPath = "D:/Projects/에어스튜디오/mytube_clone_20260828/ae_wuxia_fx/wuxia_ae_fx.avi";
var reportPath = "D:/Projects/에어스튜디오/mytube_clone_20260828/ae_wuxia_fx/wuxia_ae_fx_report.txt";

var W = 720;
var H = 720;
var DUR = 4;
var FPS = 24;

function writeReport(lines) {
  var out = new File(reportPath);
  out.encoding = "UTF-8";
  out.open("w");
  for (var i = 0; i < lines.length; i++) out.writeln(lines[i]);
  out.close();
}

function addFx(layer, matchName, label, lines) {
  var candidates = [matchName];
  if (label == "Glow") candidates = [matchName, "ADBE Glo2", "Glow"];
  if (label == "Gaussian Blur") candidates = [matchName, "ADBE Fast Blur", "ADBE Gaussian Blur", "Gaussian Blur"];

  for (var i = 0; i < candidates.length; i++) {
    try {
      var fx = layer.property("Effects").addProperty(candidates[i]);
      lines.push("effect_added=" + label + " as " + candidates[i] + " on " + layer.name);
      return fx;
    } catch (err) {
      if (i == candidates.length - 1) {
        lines.push("effect_failed=" + label + " on " + layer.name + " / " + err.toString());
      }
    }
  }
  return null;
}

function setOpacity(layer, t0, v0, t1, v1, t2, v2) {
  var p = layer.property("Opacity");
  p.setValueAtTime(t0, v0);
  p.setValueAtTime(t1, v1);
  p.setValueAtTime(t2, v2);
}

function makeStroke(comp, name, vertices, width, color, startOffset, lines) {
  var layer = comp.layers.addShape();
  layer.name = name;
  layer.property("Position").setValue([0, 0]);
  var group = layer.property("Contents").addProperty("ADBE Vector Group");
  var contents = group.property("Contents");
  var pathGroup = contents.addProperty("ADBE Vector Shape - Group");
  var shape = new Shape();
  shape.vertices = vertices;
  shape.inTangents = [];
  shape.outTangents = [];
  shape.closed = false;
  for (var i = 0; i < vertices.length; i++) {
    shape.inTangents.push([0, 0]);
    shape.outTangents.push([0, 0]);
  }
  pathGroup.property("Path").setValue(shape);

  var stroke = contents.addProperty("ADBE Vector Graphic - Stroke");
  stroke.property("Color").setValue(color);
  stroke.property("Stroke Width").setValue(width);
  stroke.property("Line Cap").setValue(2);

  var trim = contents.addProperty("ADBE Vector Filter - Trim");
  trim.property("Start").setValueAtTime(0, 72);
  trim.property("End").setValueAtTime(0, 74);
  trim.property("Start").setValueAtTime(0.8 + startOffset, 4);
  trim.property("End").setValueAtTime(1.2 + startOffset, 100);
  trim.property("Start").setValueAtTime(DUR, 0);
  trim.property("End").setValueAtTime(DUR, 100);

  layer.blendingMode = BlendingMode.ADD;
  setOpacity(layer, 0, 0, 0.8 + startOffset, 100, DUR, 45);

  addFx(layer, "ADBE Glow", "Glow", lines);
  addFx(layer, "ADBE Gaussian Blur 2", "Gaussian Blur", lines);
  return layer;
}

function makeEllipseRing(comp, name, pos, scale0, scale1, color, delay, lines) {
  var layer = comp.layers.addShape();
  layer.name = name;
  var group = layer.property("Contents").addProperty("ADBE Vector Group");
  var contents = group.property("Contents");
  var ellipse = contents.addProperty("ADBE Vector Shape - Ellipse");
  ellipse.property("Size").setValue([220, 70]);
  var stroke = contents.addProperty("ADBE Vector Graphic - Stroke");
  stroke.property("Color").setValue(color);
  stroke.property("Stroke Width").setValue(3);
  layer.property("Position").setValue(pos);
  layer.property("Rotation").setValue(-13);
  layer.property("Scale").setValueAtTime(delay, [scale0, scale0]);
  layer.property("Scale").setValueAtTime(delay + 1.2, [scale1, scale1]);
  setOpacity(layer, delay, 0, delay + 0.25, 70, delay + 1.2, 0);
  layer.blendingMode = BlendingMode.ADD;
  addFx(layer, "ADBE Glow", "Glow", lines);
  return layer;
}

function makeMote(comp, idx, lines) {
  var x = 65 + ((idx * 97) % 610);
  var y = 700 - ((idx * 53) % 500);
  var layer = comp.layers.addShape();
  layer.name = "qi_mote_" + idx;
  var group = layer.property("Contents").addProperty("ADBE Vector Group");
  var contents = group.property("Contents");
  var ellipse = contents.addProperty("ADBE Vector Shape - Ellipse");
  var size = 2 + (idx % 4);
  ellipse.property("Size").setValue([size, size]);
  var fill = contents.addProperty("ADBE Vector Graphic - Fill");
  fill.property("Color").setValue([0.70, 0.92, 1.0]);
  layer.property("Position").setValueAtTime(0, [x, y]);
  layer.property("Position").setValueAtTime(DUR, [x + 45 - (idx % 9) * 10, y - 110 - (idx % 7) * 16]);
  setOpacity(layer, 0, 0, 0.8 + (idx % 8) * 0.05, 72, DUR, 0);
  layer.blendingMode = BlendingMode.ADD;
}

var lines = [];
app.beginSuppressDialogs();

try {
  if (app.project) app.project.close(CloseOptions.DO_NOT_SAVE_CHANGES);
  app.newProject();

  var img = new File(imagePath);
  if (!img.exists) throw new Error("Image not found: " + imagePath);
  var footage = app.project.importFile(new ImportOptions(img));
  var comp = app.project.items.addComp("wuxia_sword_aura_AE_only_fx", W, H, 1, DUR, FPS);
  comp.bgColor = [0, 0, 0];

  var bg = comp.layers.add(footage);
  bg.name = "source_art";
  var scale = Math.max(W / footage.width, H / footage.height) * 100;
  bg.property("Scale").setValueAtTime(0, [scale * 1.03, scale * 1.03]);
  bg.property("Scale").setValueAtTime(DUR, [scale * 1.08, scale * 1.08]);
  bg.property("Position").setValueAtTime(0, [W / 2 + 6, H / 2 + 2]);
  bg.property("Position").setValueAtTime(DUR, [W / 2 - 10, H / 2 - 4]);

  var moonRay = comp.layers.addShape();
  moonRay.name = "volumetric_moon_ray_shapes";
  moonRay.property("Position").setValue([0, 0]);
  var moonGroup = moonRay.property("Contents").addProperty("ADBE Vector Group");
  var moonContents = moonGroup.property("Contents");
  var rayPath = moonContents.addProperty("ADBE Vector Shape - Group");
  var rayShape = new Shape();
  rayShape.vertices = [[560, 74], [720, 152], [720, 345], [430, 510], [500, 260]];
  rayShape.inTangents = [[0,0],[0,0],[0,0],[0,0],[0,0]];
  rayShape.outTangents = [[0,0],[0,0],[0,0],[0,0],[0,0]];
  rayShape.closed = true;
  rayPath.property("Path").setValue(rayShape);
  var rayFill = moonContents.addProperty("ADBE Vector Graphic - Fill");
  rayFill.property("Color").setValue([0.55, 0.72, 1.0]);
  moonRay.blendingMode = BlendingMode.ADD;
  setOpacity(moonRay, 0, 0, 1.0, 19, DUR, 8);
  addFx(moonRay, "ADBE Gaussian Blur 2", "Gaussian Blur", lines);

  var fog = comp.layers.addSolid([0.35, 0.38, 0.40], "fractal_moving_fog", W, H, 1, DUR);
  fog.blendingMode = BlendingMode.SCREEN;
  setOpacity(fog, 0, 0, 1.1, 32, DUR, 22);
  var fractal = addFx(fog, "ADBE Fractal Noise", "Fractal Noise", lines);
  if (fractal) {
    try {
      fractal.property("Contrast").setValue(160);
      fractal.property("Brightness").setValue(-50);
      fractal.property("Evolution").setValueAtTime(0, 0);
      fractal.property("Evolution").setValueAtTime(DUR, 260);
    } catch (err1) {
      lines.push("fractal_tweak_failed=" + err1.toString());
    }
  }
  addFx(fog, "ADBE Turbulent Displace", "Turbulent Displace", lines);
  addFx(fog, "ADBE Gaussian Blur 2", "Gaussian Blur", lines);

  makeStroke(comp, "blade_inner_blue_core", [[110, 84], [145, 245], [184, 408], [215, 575]], 7, [0.60, 0.88, 1.0], 0, lines);
  makeStroke(comp, "blade_outer_white_qi", [[100, 72], [138, 240], [178, 420], [210, 592]], 18, [0.25, 0.65, 1.0], 0.08, lines);
  makeStroke(comp, "flying_sword_arc_01", [[80, 505], [230, 415], [402, 330], [625, 180]], 5, [0.72, 0.90, 1.0], 0.16, lines);
  makeStroke(comp, "flying_sword_arc_02", [[54, 620], [210, 504], [480, 420], [700, 320]], 4, [0.45, 0.78, 1.0], 0.32, lines);

  makeEllipseRing(comp, "qi_ring_ground_01", [184, 568], 35, 185, [0.55, 0.88, 1.0], 0.45, lines);
  makeEllipseRing(comp, "qi_ring_ground_02", [184, 568], 20, 245, [0.42, 0.70, 1.0], 1.15, lines);

  for (var i = 0; i < 54; i++) makeMote(comp, i, lines);

  var pulse = comp.layers.addSolid([0.58, 0.78, 1.0], "blue_qi_pulse_additive", W, H, 1, DUR);
  pulse.blendingMode = BlendingMode.ADD;
  setOpacity(pulse, 0, 0, 1.05, 16, 1.35, 0);
  pulse.property("Opacity").setValueAtTime(2.4, 10);
  pulse.property("Opacity").setValueAtTime(2.75, 0);
  addFx(pulse, "ADBE Glow", "Glow", lines);

  var warp = comp.layers.addSolid([0.5, 0.5, 0.5], "heat_distortion_adjustment", W, H, 1, DUR);
  warp.adjustmentLayer = true;
  setOpacity(warp, 0, 0, 1.0, 45, DUR, 10);
  addFx(warp, "ADBE Turbulent Displace", "Turbulent Displace", lines);

  var vignette = comp.layers.addSolid([0, 0, 0], "ink_vignette", W, H, 1, DUR);
  vignette.blendingMode = BlendingMode.MULTIPLY;
  setOpacity(vignette, 0, 18, DUR / 2, 38, DUR, 25);
  addFx(vignette, "ADBE Radial Wipe", "Radial Wipe", lines);

  var rqItem = app.project.renderQueue.items.add(comp);
  rqItem.outputModule(1).file = new File(renderPath);
  app.project.save(new File(projectPath));
  lines.push("project_saved=" + projectPath);
  lines.push("render_queued=" + renderPath);
} catch (err) {
  lines.push("ERROR=" + err.toString());
} finally {
  writeReport(lines);
  app.endSuppressDialogs(false);
}
