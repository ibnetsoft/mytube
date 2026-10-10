"""After Effects ExtendScript for structured manga motion scenes.

The templates require a genuine, full-canvas layered PSD. A flattened scene
image is deliberately not accepted: it cannot animate three independent
characters or keep effects aligned to a separate talisman.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


MANGA_TEMPLATES = frozenset({
    "parallax_layered_scene",
    "directed_performance",
    "dialogue_closeup",
    "angled_triple_reaction", "body_following_qi", "ink_splat_impact",
    "wall_impact_debris", "glasses_reflection", "kinetic_title_reveal",
    "backlit_hand_reveal",
})


def template_for_scene(scene: dict[str, Any]) -> str:
    plan = scene.get("ae_effect_plan")
    if not isinstance(plan, dict) or not plan.get("enabled"):
        return ""
    name = str(plan.get("template") or "").strip()
    return name if name in MANGA_TEMPLATES else ""


def write_manga_jsx(
    *, scene: dict[str, Any], input_psd: Path, project_path: Path,
    render_path: Path, jsx_path: Path, comp_name: str,
    width: int, height: int, fps: int, duration: float,
    layer_centers: dict[str, list[float]] | None = None,
) -> None:
    plan = scene.get("ae_effect_plan") or {}
    template = template_for_scene(scene)
    if not template or input_psd.suffix.lower() != ".psd":
        raise ValueError("A manga template requires an enabled plan and a layered PSD")
    config = {
        "template": template,
        "plan": plan,
        "runtime": scene.get("ae_mouth_runtime") if isinstance(scene.get("ae_mouth_runtime"), dict) else {"enabled": False},
        "layer_centers": layer_centers or {},
        "source": input_psd.resolve().as_posix(),
        "project": project_path.resolve().as_posix(),
        "render": render_path.resolve().as_posix(),
        "status": jsx_path.with_suffix(".status.txt").resolve().as_posix(),
        "comp": comp_name,
        "width": width, "height": height, "fps": fps, "duration": duration,
    }
    jsx_path.write_text(
        _JSX.replace("__MANGA_CONFIG__", json.dumps(config, ensure_ascii=True)),
        encoding="utf-8",
    )


_JSX = r'''// Generated manga scene. Full-canvas PSD layers have semantic role names.
var CFG = __MANGA_CONFIG__;
app.exitAfterLaunchAndEval = true;
var W = CFG.width, H = CFG.height, DUR = CFG.duration, FPS = CFG.fps;
var PLAN = CFG.plan;
var RUNTIME = CFG.runtime || {enabled:false};
function pxX(x) { return Number(x) * W; }
function pxY(y) { return Number(y) * H; }
function alignLayer(role, x, y) {
  var center = CFG.layer_centers[role] || [0.5, 0.5];
  return [W/2 + (Number(x) - Number(center[0])) * W,
          H/2 + (Number(y) - Number(center[1])) * H];
}
function at(t) { return Math.max(0, Math.min(DUR, Number(t))); }
function clamp01(x) { return Math.max(0, Math.min(1, Number(x))); }
function effect(layer, matchName) {
  try { return layer.property("Effects").addProperty(matchName); } catch (e) { return null; }
}
function setFade(layer, begin, peak, end) {
  var p = layer.property("Opacity");
  p.setValueAtTime(at(begin), 0);
  p.setValueAtTime(at(peak), 100);
  if (end !== null) p.setValueAtTime(at(end), 0);
}
function revealOnBeat(layer, when) {
  layer.inPoint = at(when);
  layer.property("Opacity").setValue(100);
}
function firstBeat(action, fallback) {
  var beats = PLAN.beats || [];
  for (var i = 0; i < beats.length; i++) {
    if (beats[i].action == action) return Number(beats[i].at_seconds);
  }
  return fallback;
}
function firstBeatText(action, fallback) {
  var beats = PLAN.beats || [];
  for (var i = 0; i < beats.length; i++) {
    if (beats[i].action == action && beats[i].text) return String(beats[i].text);
  }
  return fallback;
}
function polygon(comp, name, coords, fillColor, strokeColor, strokeWidth) {
  var layer = comp.layers.addShape();
  layer.name = name;
  layer.property("Position").setValue([0, 0]);
  var group = layer.property("Contents").addProperty("ADBE Vector Group");
  var contents = group.property("Contents");
  var shapeGroup = contents.addProperty("ADBE Vector Shape - Group");
  var shape = new Shape();
  var vertices = [], inTangents = [], outTangents = [];
  for (var i = 0; i < coords.length; i++) {
    vertices.push([pxX(coords[i][0]), pxY(coords[i][1])]);
    inTangents.push([0, 0]); outTangents.push([0, 0]);
  }
  shape.vertices = vertices; shape.inTangents = inTangents; shape.outTangents = outTangents;
  shape.closed = true;
  shapeGroup.property("Path").setValue(shape);
  if (fillColor !== null) {
    var fill = contents.addProperty("ADBE Vector Graphic - Fill");
    fill.property("Color").setValue(fillColor);
  }
  if (strokeColor !== null) {
    var stroke = contents.addProperty("ADBE Vector Graphic - Stroke");
    stroke.property("Color").setValue(strokeColor);
    stroke.property("Stroke Width").setValue(strokeWidth);
  }
  return layer;
}
function line(comp, name, coords, color, width, start, end, glow) {
  var layer = comp.layers.addShape();
  layer.name = name;
  layer.property("Position").setValue([0, 0]);
  var group = layer.property("Contents").addProperty("ADBE Vector Group");
  var contents = group.property("Contents");
  var pathGroup = contents.addProperty("ADBE Vector Shape - Group");
  var shape = new Shape();
  var vertices = [], inTangents = [], outTangents = [];
  for (var i = 0; i < coords.length; i++) {
    vertices.push([pxX(coords[i][0]), pxY(coords[i][1])]);
    inTangents.push([0, 0]); outTangents.push([0, 0]);
  }
  shape.vertices = vertices; shape.inTangents = inTangents; shape.outTangents = outTangents;
  shape.closed = false;
  pathGroup.property("Path").setValue(shape);
  var stroke = contents.addProperty("ADBE Vector Graphic - Stroke");
  stroke.property("Color").setValue(color);
  stroke.property("Stroke Width").setValue(width);
  stroke.property("Line Cap").setValue(2);
  var trim = contents.addProperty("ADBE Vector Filter - Trim");
  trim.property("End").setValueAtTime(at(start), 0);
  trim.property("End").setValueAtTime(at(end), 100);
  if (glow) { layer.blendingMode = BlendingMode.ADD; effect(layer, "ADBE Glo2"); }
  return layer;
}
function text(comp, name, value, x, y, size, color, strokeColor, start, finish) {
  var layer = comp.layers.addText(String(value));
  layer.name = name;
  var doc = layer.property("Source Text").value;
  doc.fontSize = size;
  doc.fillColor = color;
  doc.applyFill = true;
  if (strokeColor !== null) {
    doc.strokeColor = strokeColor;
    doc.strokeWidth = Math.max(2, size * 0.045);
    doc.applyStroke = true;
    doc.strokeOverFill = false;
  } else {
    doc.applyStroke = false;
  }
  doc.justification = ParagraphJustification.CENTER_JUSTIFY;
  layer.property("Source Text").setValue(doc);
  layer.property("Position").setValue([pxX(x), pxY(y)]);
  revealOnBeat(layer, start);
  if (finish !== null) {
    layer.property("Opacity").setValueAtTime(at(start), 100);
    layer.property("Opacity").setValueAtTime(at(finish), 0);
  }
  layer.property("Scale").setValueAtTime(at(start), [80, 80]);
  layer.property("Scale").setValueAtTime(at(start + 0.16), [110, 110]);
  layer.property("Scale").setValueAtTime(at(start + 0.28), [100, 100]);
  return layer;
}
function layerByRole(comp, role, required) {
  var source = SOURCES[role];
  if (!source && required) throw "PSD layer is missing: " + role;
  if (!source) return null;
  var layer = comp.layers.add(source.source);
  layer.name = role;
  layer.property("Position").setValue([W / 2, H / 2]);
  return layer;
}
function finiteNumber(value, fallback, minimum, maximum) {
  var number = Number(value);
  if (!isFinite(number)) number = fallback;
  return Math.max(minimum, Math.min(maximum, number));
}
function animateParallaxLayer(layer, role, fallbackDepth) {
  var animation = PLAN.layer_animation || {};
  var camera = animation.camera || {};
  var values = animation[role] || {};
  var depth = finiteNumber(values.depth, fallbackDepth, 0, 1.25);
  var cameraZoom = finiteNumber(camera.zoom, 0.025, 0, 0.08);
  var scaleMove = finiteNumber(values.scale, cameraZoom * depth, 0, 0.10);
  var moveX = finiteNumber(values.move_x, finiteNumber(camera.pan_x, 0.006, -0.03, 0.03) * depth, -0.03, 0.03);
  var moveY = finiteNumber(values.move_y, finiteNumber(camera.pan_y, -0.003, -0.03, 0.03) * depth, -0.03, 0.03);
  var rotation = finiteNumber(values.rotation, 0, -1.0, 1.0);
  layer.property("Scale").setValueAtTime(0, [100,100]);
  layer.property("Scale").setValueAtTime(DUR, [100 + scaleMove * 100,100 + scaleMove * 100]);
  layer.property("Position").setValueAtTime(0, [W/2 - moveX * W/2,H/2 - moveY * H/2]);
  layer.property("Position").setValueAtTime(DUR, [W/2 + moveX * W/2,H/2 + moveY * H/2]);
  if (rotation) {
    layer.property("Rotation").setValueAtTime(0, -rotation / 2);
    layer.property("Rotation").setValueAtTime(DUR, rotation / 2);
  }
}
function blurLayer(layer, amount) {
  amount = finiteNumber(amount, 0, 0, 4);
  if (!amount) return;
  var blur = effect(layer, "ADBE Gaussian Blur 2");
  if (blur) {
    try { blur.property(1).setValue(amount); } catch (ignoreBlur) {}
  }
}
function addRuntimePatches(comp, character) {
  if (!RUNTIME.enabled || !character) return;
  var poses = ["closed", "half", "open"];
  var speakers = RUNTIME.speakers || [];
  for (var si = 0; si < speakers.length; si++) {
    var speaker = speakers[si];
    for (var pi = 0; pi < poses.length; pi++) {
      var pose = poses[pi];
      if (!speaker.layers || !speaker.layers[pose]) continue;
      var patch = app.project.importFile(new ImportOptions(new File(speaker.layers[pose])));
      var mouth = comp.layers.add(patch);
      mouth.name = "mouth_" + si + "_" + pose;
      mouth.property("Position").setValue([
        Math.round(Number(speaker.mouth_box[0]) * W) + patch.width / 2,
        Math.round(Number(speaker.mouth_box[1]) * H) + patch.height / 2]);
      var opacity = mouth.property("Opacity");
      var cues = speaker.cues || [];
      for (var ci = 0; ci < cues.length; ci++) {
        var key = opacity.addKey(at(cues[ci].at_seconds));
        opacity.setValueAtKey(key, cues[ci].pose == pose ? 100 : 0);
        opacity.setInterpolationTypeAtKey(key, KeyframeInterpolationType.HOLD, KeyframeInterpolationType.HOLD);
      }
      mouth.parent = character;
    }
  }
  var blinks = RUNTIME.blinks || [];
  var sides = ["left", "right"];
  for (var bi = 0; bi < blinks.length; bi++) {
    var blink = blinks[bi];
    for (var ei = 0; ei < sides.length; ei++) {
      var side = sides[ei];
      if (!blink.layers || !blink.layers[side]) continue;
      var box = side == "left" ? blink.left_eye_box : blink.right_eye_box;
      var eyePatch = app.project.importFile(new ImportOptions(new File(blink.layers[side])));
      var eye = comp.layers.add(eyePatch);
      eye.name = "blink_" + bi + "_" + side;
      eye.property("Position").setValue([
        Math.round(Number(box[0]) * W) + eyePatch.width / 2,
        Math.round(Number(box[1]) * H) + eyePatch.height / 2]);
      var eyeOpacity = eye.property("Opacity");
      var eyeCues = blink.cues || [];
      for (var ec = 0; ec < eyeCues.length; ec++) {
        var eyeKey = eyeOpacity.addKey(at(eyeCues[ec].at_seconds));
        eyeOpacity.setValueAtKey(eyeKey, eyeCues[ec].opacity);
        eyeOpacity.setInterpolationTypeAtKey(eyeKey, KeyframeInterpolationType.LINEAR, KeyframeInterpolationType.LINEAR);
      }
      eye.parent = character;
    }
  }
}
function maskPolygon(layer, polygonCoords) {
  var mask = layer.Masks.addProperty("Mask");
  var shape = new Shape();
  var vertices = [], inTangents = [], outTangents = [];
  for (var i = 0; i < polygonCoords.length; i++) {
    vertices.push([pxX(polygonCoords[i][0]), pxY(polygonCoords[i][1])]);
    inTangents.push([0, 0]); outTangents.push([0, 0]);
  }
  shape.vertices = vertices; shape.inTangents = inTangents; shape.outTangents = outTangents;
  shape.closed = true;
  mask.property("Mask Path").setValue(shape);
  mask.property("Mask Feather").setValue([0, 0]);
}
function speedLines(comp, center, start) {
  for (var i = 0; i < 20; i++) {
    var angle = Math.PI * 2 * i / 20;
    var c = [Number(center[0]), Number(center[1])];
    var r0 = 0.11, r1 = 0.65 + (i % 4) * 0.04;
    line(comp, "radial_speed_" + i,
      [[c[0] + Math.cos(angle) * r0, c[1] + Math.sin(angle) * r0],
       [c[0] + Math.cos(angle) * r1, c[1] + Math.sin(angle) * r1]],
      [0.93, 0.92, 1], 2 + i % 3, start, start + 0.35, false);
  }
}
function speechBubble(comp, start) {
  var bubble = polygon(comp, "reaction_bubble", PLAN.bubble_polygon ||
    [[0.275,0.07],[0.405,0.08],[0.415,0.30],[0.34,0.35],[0.30,0.43],[0.30,0.32],[0.275,0.30]],
    [1,1,1], [0.03,0.03,0.04], 5);
  setFade(bubble, start, start + 0.1, null);
  var value = "?!";
  var beats = PLAN.beats || [];
  for (var i = 0; i < beats.length; i++) if (beats[i].action == "speech_bubble" && beats[i].text) value = beats[i].text;
  text(comp, "reaction_bubble_text", value, 0.348, 0.255, Math.round(H * 0.13), [0,0,0], null,
       start + 0.04, null);
}
function dialogueCloseup(comp) {
  var face = layerByRole(comp, "character", true);
  var start = firstBeat("camera_push", 0.25);
  face.property("Scale").setValueAtTime(0, [100,100]);
  face.property("Scale").setValueAtTime(at(start), [101,101]);
  face.property("Scale").setValueAtTime(DUR, [108,108]);
  var sync = PLAN.lip_sync || {};
  if (!sync.enabled) return;
  var roles = ["mouth_closed", "mouth_half", "mouth_open"];
  var poses = ["closed", "half", "open"];
  for (var i = 0; i < roles.length; i++) {
    var mouth = layerByRole(comp, roles[i], true);
    mouth.property("Scale").setValueAtTime(0, [100,100]);
    mouth.property("Scale").setValueAtTime(at(start), [101,101]);
    mouth.property("Scale").setValueAtTime(DUR, [108,108]);
    var opacity = mouth.property("Opacity");
    var cues = sync.cues || [];
    for (var j = 0; j < cues.length; j++) {
      var key = opacity.addKey(at(cues[j].at_seconds));
      opacity.setValueAtKey(key, cues[j].pose == poses[i] ? 100 : 0);
      opacity.setInterpolationTypeAtKey(key, KeyframeInterpolationType.HOLD, KeyframeInterpolationType.HOLD);
    }
  }
}
function parallaxLayeredScene(comp) {
  var background = comp.layer("background");
  var character = layerByRole(comp, "character", true);
  var animation = PLAN.layer_animation || {};
  animateParallaxLayer(background, "background", 0.20);
  blurLayer(background, (animation.background || {}).blur);
  animateParallaxLayer(character, "character", 0.62);
  blurLayer(character, (animation.character || {}).blur);
  addRuntimePatches(comp, character);
  var hairCloth = layerByRole(comp, "hair_cloth", false);
  var foreground = layerByRole(comp, "foreground", true);
  var prop = layerByRole(comp, "prop_focus", false);
  var atmosphere = layerByRole(comp, "atmosphere", false);
  var lightOverlay = layerByRole(comp, "light_overlay", false);
  animateParallaxLayer(foreground, "foreground", 1.0);
  blurLayer(foreground, (animation.foreground || {}).blur);
  if (prop) {
    animateParallaxLayer(prop, "prop_focus", 0.82);
    blurLayer(prop, (animation.prop_focus || {}).blur);
  }
  if (hairCloth) {
    var sway = finiteNumber((animation.hair_cloth || {}).sway_degrees, 0.55, 0, 1.5);
    var center = CFG.layer_centers.hair_cloth || [0.5,0.5];
    hairCloth.property("Anchor Point").setValue([pxX(center[0]),pxY(center[1])]);
    hairCloth.property("Position").setValue([pxX(center[0]),pxY(center[1])]);
    hairCloth.property("Rotation").setValueAtTime(0, -sway);
    hairCloth.property("Rotation").setValueAtTime(DUR / 2, sway);
    hairCloth.property("Rotation").setValueAtTime(DUR, -sway);
  }
  if (atmosphere) {
    atmosphere.blendingMode = BlendingMode.SCREEN;
    var amin = finiteNumber((animation.atmosphere || {}).opacity_min, 18, 0, 45);
    var amax = finiteNumber((animation.atmosphere || {}).opacity_max, 34, amin, 55);
    atmosphere.property("Opacity").setValueAtTime(0, amin);
    atmosphere.property("Opacity").setValueAtTime(DUR / 2, amax);
    atmosphere.property("Opacity").setValueAtTime(DUR, amin);
  }
  if (lightOverlay) {
    lightOverlay.blendingMode = BlendingMode.ADD;
    var lmin = finiteNumber((animation.light_overlay || {}).opacity_min, 12, 0, 35);
    var lmax = finiteNumber((animation.light_overlay || {}).opacity_max, 28, lmin, 45);
    lightOverlay.property("Opacity").setValueAtTime(0, lmin);
    lightOverlay.property("Opacity").setValueAtTime(DUR / 2, lmax);
    lightOverlay.property("Opacity").setValueAtTime(DUR, lmin);
  }
}
function triple(comp) {
  speedLines(comp, [0.5, 0.47], firstBeat("background_speedline_in", 0.05));
  var panels = PLAN.panels || [];
  for (var i = 0; i < panels.length; i++) {
    var p = panels[i];
    var role = String(p.role);
    var actor = layerByRole(comp, role, true);
    maskPolygon(actor, p.polygon);
    var start = Number(p.enter_at || 0);
    var drift = role == "character_left" ? -14 : role == "character_right" ? 14 : 0;
    actor.property("Position").setValueAtTime(0, [W/2 + drift, H/2 + 5]);
    actor.property("Position").setValueAtTime(DUR, [W/2 - drift, H/2 - 5]);
    actor.property("Scale").setValueAtTime(0, [101,101]);
    actor.property("Scale").setValueAtTime(DUR, [105,105]);
    setFade(actor, start, start + 0.12, null);
    polygon(comp, "panel_border_" + role, p.polygon, null, [0.035,0.025,0.05], 8);
  }
  speechBubble(comp, firstBeat("speech_bubble", 0.38));
}
function qi(comp) {
  var character = layerByRole(comp, "character", true);
  character.property("Scale").setValueAtTime(0, [100,100]);
  character.property("Scale").setValueAtTime(DUR, [104,104]);
  var talisman = layerByRole(comp, "talisman", true);
  talisman.property("Scale").setValueAtTime(0, [100,100]);
  talisman.property("Scale").setValueAtTime(DUR, [107,107]);
  var attach = firstBeat("talisman_attach", 0.2);
  var target = PLAN.talisman_target || [0.5, 0.6];
  var attached = alignLayer("talisman", target[0], target[1]);
  talisman.property("Position").setValueAtTime(at(Math.max(0, attach - 0.16)),
      [attached[0] + 30, attached[1] - 25]);
  talisman.property("Position").setValueAtTime(at(attach), attached);
  revealOnBeat(talisman, attach);
  var begin = firstBeat("qi_trace_start", 0.35);
  var path = PLAN.qi_path || [];
  line(comp, "body_qi_outer", path, [0.93,0.10,0.78], 22, begin, begin + 1.2, true);
  line(comp, "body_qi_inner", path, [1,0.72,0.96], 7, begin + 0.05, begin + 1.15, true);
  var overlay = layerByRole(comp, "qi_overlay", false);
  if (overlay) {
    overlay.blendingMode = BlendingMode.ADD;
    setFade(overlay, begin, begin + 0.22, Math.min(DUR, begin + 1.6));
    effect(overlay, "ADBE Glo2");
  }
  var shake = character.property("Position");
  shake.setValueAtTime(at(begin), [W/2,H/2]);
  shake.setValueAtTime(at(begin + 0.08), [W/2 + 11,H/2 - 6]);
  shake.setValueAtTime(at(begin + 0.16), [W/2 - 8,H/2 + 5]);
  shake.setValueAtTime(at(begin + 0.26), [W/2,H/2]);
  var beats = PLAN.beats || [];
  for (var i = 0; i < beats.length; i++) {
    if (beats[i].action == "caption" && beats[i].text) {
      text(comp, "shock_caption", beats[i].text, 0.5, 0.82, Math.round(H * 0.065),
           [0.9,0.08,0.04], [0.02,0,0], Number(beats[i].at_seconds), null);
    }
  }
}
function starPoints(cx, cy, outer, inner, count) {
  var points = [];
  for (var i = 0; i < count * 2; i++) {
    var a = Math.PI * i / count;
    var radius = (i % 2 == 0 ? outer : inner) * (0.84 + (i * 13 % 7) * 0.045);
    points.push([cx + Math.cos(a) * radius, cy + Math.sin(a) * radius]);
  }
  return points;
}
function ellipsePoints(cx, cy, rx, ry, count) {
  var points = [];
  for (var i = 0; i < count; i++) {
    var angle = Math.PI * 2 * i / count;
    points.push([cx + Math.cos(angle) * rx, cy + Math.sin(angle) * ry]);
  }
  return points;
}
function impact(comp) {
  var character = layerByRole(comp, "character", true);
  character.property("Scale").setValueAtTime(0, [100,100]);
  character.property("Scale").setValueAtTime(DUR, [108,108]);
  var talisman = layerByRole(comp, "talisman", true);
  var imp = PLAN.impact || {};
  var x = Number(imp.x), y = Number(imp.y), moment = Number(imp.at_seconds);
  var strikeAt = firstBeat("talisman_strike", Math.max(0, moment - 0.16));
  var inkAt = firstBeat("ink_splat", moment + 0.06);
  var letteringAt = firstBeat("onomatopoeia", moment + 0.12);
  var struck = alignLayer("talisman", x, y);
  talisman.property("Position").setValueAtTime(at(strikeAt), [struck[0] + 46,struck[1] - 35]);
  talisman.property("Position").setValueAtTime(at(moment), struck);
  talisman.property("Position").setValueAtTime(at(moment + 0.09), [struck[0] + 18,struck[1] - 13]);
  talisman.property("Position").setValueAtTime(at(moment + 0.2), struck);
  var spark = polygon(comp, "talisman_contact_flash", starPoints(x,y,0.13,0.045,14),
                      [1,0.70,0.12], null, 0);
  spark.blendingMode = BlendingMode.ADD;
  setFade(spark, moment, moment + 0.04, moment + 0.38);
  effect(spark, "ADBE Glo2");
  speedLines(comp, [x,y], moment);
  var splat = layerByRole(comp, "ink_splat", false);
  if (!splat) splat = polygon(comp, "procedural_ink_splat", starPoints(x + 0.15,y - 0.08,0.18,0.10,23),
                              [0.025,0.005,0.015], null, 0);
  splat.name = "ink_splat";
  splat.property("Anchor Point").setValue([pxX(x + 0.15), pxY(y - 0.08)]);
  splat.property("Position").setValue([pxX(x + 0.15), pxY(y - 0.08)]);
  splat.property("Scale").setValueAtTime(at(inkAt), [20,20]);
  splat.property("Scale").setValueAtTime(at(inkAt + 0.18), [115,115]);
  splat.property("Scale").setValueAtTime(at(inkAt + 0.32), [100,100]);
  revealOnBeat(splat, inkAt);
  var red = polygon(comp, "red_impact_core", starPoints(x + 0.15,y - 0.08,0.105,0.055,15),
                    [0.82,0.035,0.02], null, 0);
  red.blendingMode = BlendingMode.ADD;
  revealOnBeat(red, inkAt);
  text(comp, "impact_onomatopoeia", firstBeatText("onomatopoeia", imp.text || "펑!"), x + 0.15, y - 0.05,
       Math.round(H * 0.085), [1,1,1], [0.52,0,0], letteringAt, null);
  var flash = comp.layers.addSolid([1,1,1], "impact_white_flash", W, H, 1, DUR);
  flash.blendingMode = BlendingMode.ADD;
  var op = flash.property("Opacity");
  op.setValueAtTime(at(moment), 0);
  op.setValueAtTime(at(moment + 1 / FPS), 52);
  op.setValueAtTime(at(moment + 3 / FPS), 0);
}
function wallImpact(comp) {
  var imp = PLAN.impact || {}, x = Number(imp.x), y = Number(imp.y);
  var contact = firstBeat("wall_contact", Number(imp.at_seconds));
  var burst = firstBeat("debris_burst", contact + 0.06);
  var reveal = firstBeat("wall_reveal", contact + 0.12);
  var settle = firstBeat("debris_settle", contact + 0.7);
  var intact = layerByRole(comp, "wall_intact", true);
  var broken = layerByRole(comp, "wall_broken", true);
  revealOnBeat(broken, reveal);
  intact.property("Opacity").setValueAtTime(at(Math.max(0, reveal - 1/FPS)), 100);
  intact.property("Opacity").setValueAtTime(at(reveal), 0);
  var character = layerByRole(comp, "character", true);
  var target = alignLayer("character", x, y);
  var pos = character.property("Position");
  pos.setValueAtTime(at(Math.max(0, contact - 0.3)), [target[0] + W*0.10, target[1] - H*0.07]);
  pos.setValueAtTime(at(contact), [target[0], target[1]]);
  pos.setValueAtTime(at(contact + 0.08), [target[0] - 13, target[1] + 8]);
  pos.setValueAtTime(at(contact + 0.16), [target[0] + 7, target[1] - 4]);
  pos.setValueAtTime(at(settle), target);
  character.property("Rotation").setValueAtTime(at(Math.max(0, contact - 0.3)), 7);
  character.property("Rotation").setValueAtTime(at(contact), -4);
  character.property("Rotation").setValueAtTime(at(settle), 0);
  var artLines = layerByRole(comp, "speedlines", false);
  if (artLines) setFade(artLines, contact, contact + 0.08, contact + 0.48);
  speedLines(comp, [x,y], contact);
  var artDebris = layerByRole(comp, "debris", false);
  if (artDebris) {
    revealOnBeat(artDebris, burst);
    artDebris.property("Scale").setValueAtTime(at(burst), [70,70]);
    artDebris.property("Scale").setValueAtTime(at(burst + 0.28), [109,109]);
    artDebris.property("Scale").setValueAtTime(at(settle), [100,100]);
  }
  for (var i = 0; i < 15; i++) {
    var angle = 2*Math.PI*i/15, radius = 0.016 + (i%4)*0.007;
    var cx = x + Math.cos(angle)*0.09, cy = y + Math.sin(angle)*0.09;
    var shard = polygon(comp, "wall_shard_" + i,
      [[cx-radius,cy-radius],[cx+radius,cy-radius*0.4],[cx+radius*0.2,cy+radius]],
      (i%2) ? [0.93,0.91,0.84] : [0.49,0.48,0.45], [0.13,0.12,0.12], 2);
    revealOnBeat(shard, burst);
    shard.property("Position").setValueAtTime(at(burst), [0,0]);
    shard.property("Position").setValueAtTime(at(burst + 0.52),
      [Math.cos(angle)*W*(0.06+(i%3)*0.025), Math.sin(angle)*H*(0.05+(i%4)*0.018)]);
    shard.property("Opacity").setValueAtTime(at(burst), 100);
    shard.property("Opacity").setValueAtTime(at(settle), 0);
  }
  var flash = comp.layers.addSolid([1,1,1], "wall_contact_flash", W, H, 1, DUR);
  flash.blendingMode = BlendingMode.ADD;
  flash.property("Opacity").setValueAtTime(at(contact), 0);
  flash.property("Opacity").setValueAtTime(at(contact+1/FPS), 58);
  flash.property("Opacity").setValueAtTime(at(contact+3/FPS), 0);
}
function glassesReflection(comp) {
  var face = layerByRole(comp, "character", true);
  face.property("Scale").setValueAtTime(0, [100,100]);
  face.property("Scale").setValueAtTime(DUR, [107,107]);
  var reflection = PLAN.reflection || {};
  var reveal = firstBeat("reflection_reveal", Number(reflection.at_seconds));
  var glint = firstBeat("lens_glint", reveal + 0.28);
  var push = firstBeat("camera_push", reveal + 0.12);
  face.property("Scale").setValueAtTime(at(push), [102,102]);
  face.property("Scale").setValueAtTime(DUR, [110,110]);
  var sides = ["left_lens", "right_lens"];
  for (var i = 0; i < sides.length; i++) {
    var lens = reflection[sides[i]];
    var cx = Number(lens.center[0]), cy = Number(lens.center[1]);
    var rx = Number(lens.radius[0]), ry = Number(lens.radius[1]);
    var plate = layerByRole(comp, "reflection_scene", true);
    plate.name = "reflection_" + sides[i];
    var sourceCenter = CFG.layer_centers.reflection_scene || [0.5,0.5];
    var dx = pxX(cx - Number(sourceCenter[0]));
    var dy = pxY(cy - Number(sourceCenter[1]));
    plate.property("Position").setValue([W/2+dx,H/2+dy]);
    maskPolygon(plate, ellipsePoints(cx-dx/W,cy-dy/H,rx,ry,32));
    revealOnBeat(plate, reveal);
    plate.property("Opacity").setValueAtTime(at(reveal), 0);
    plate.property("Opacity").setValueAtTime(at(reveal+0.22), 85);
    polygon(comp, "lens_rim_" + sides[i], ellipsePoints(cx,cy,rx,ry,32),
      null, [0.035,0.045,0.075], 8);
    var slash = line(comp, "lens_glint_" + sides[i],
      [[cx-rx*0.65,cy+ry*0.75],[cx+rx*0.35,cy-ry*0.72]],
      [1,1,1], 8, glint+i*0.06, glint+0.2+i*0.06, true);
    slash.property("Opacity").setValueAtTime(at(glint+i*0.06), 0);
    slash.property("Opacity").setValueAtTime(at(glint+0.06+i*0.06), 90);
    slash.property("Opacity").setValueAtTime(at(glint+0.35+i*0.06), 0);
  }
  var artGlint = layerByRole(comp, "lens_glint", false);
  if (artGlint) {
    artGlint.blendingMode = BlendingMode.ADD;
    setFade(artGlint, glint, glint+0.09, glint+0.38);
    effect(artGlint, "ADBE Glo2");
  }
}
function kineticTitle(comp) {
  var title = PLAN.title || {}, accent = String(title.accent_text || "");
  var style = String(title.style || "threat_red");
  var start = firstBeat("text_reveal", Number(title.at_seconds));
  var punch = firstBeat("text_punch", start + 0.18);
  var hold = firstBeat("text_hold", Math.min(DUR, punch + 0.75));
  var x = Number(title.position[0]), y = Number(title.position[1]);
  var prop = layerByRole(comp, "training_prop", style == "training_emphasis");
  if (prop) {
    prop.property("Scale").setValueAtTime(0, [100,100]);
    prop.property("Scale").setValueAtTime(DUR, [105,105]);
  }
  var backdrop = layerByRole(comp, "title_backdrop", false);
  if (backdrop) setFade(backdrop, start, start+0.12, null);
  var character = layerByRole(comp, "character", true);
  character.property("Scale").setValueAtTime(0, [100,100]);
  character.property("Scale").setValueAtTime(DUR, [104,104]);
  var lines = layerByRole(comp, "speedlines", false);
  if (lines) setFade(lines, punch, punch+0.09, hold);
  if (style == "training_emphasis") speedLines(comp, [x,y], punch);
  var headline = String(title.text || "");
  var atAccent = headline.indexOf(accent);
  function units(value) {
    var result = 0;
    for (var i = 0; i < value.length; i++) {
      var code = value.charCodeAt(i);
      result += value.charAt(i) == " " ? 0.35 : code > 0x2e80 ? 1.0 : 0.62;
    }
    return Math.max(1, result);
  }
  function fittedSize(value, base) {
    return Math.max(30, Math.min(Math.round(base), Math.floor(W*0.78/units(value))));
  }
  function punchScale(layer) {
    layer.property("Scale").setValueAtTime(at(punch), [65,65]);
    layer.property("Scale").setValueAtTime(at(punch+0.11), [118,118]);
    layer.property("Scale").setValueAtTime(at(punch+0.25), [100,100]);
  }
  if (style == "training_emphasis") {
    var redPart = atAccent >= 0 ? headline.substring(0, atAccent + accent.length) : headline;
    var whitePart = atAccent >= 0 ? headline.substring(atAccent + accent.length) : "";
    var size = fittedSize(headline, H*0.11);
    var red = text(comp, "kinetic_title_main", redPart,
      x, y, size, [0.98,0.12,0.07], [0.02,0,0], punch, null);
    punchScale(red);
    if (whitePart) {
      var white = text(comp, "kinetic_title_tail", whitePart,
        x, y, size,
        [1,1,1], [0.02,0.02,0.02], punch, null);
      punchScale(white);
      var redWidth = red.sourceRectAtTime(at(punch+0.3), false).width;
      var whiteWidth = white.sourceRectAtTime(at(punch+0.3), false).width;
      var gap = size*0.12, total = redWidth + whiteWidth + gap;
      red.property("Position").setValue([pxX(x)-total/2+redWidth/2, pxY(y)]);
      white.property("Position").setValue([pxX(x)+total/2-whiteWidth/2, pxY(y)]);
    }
  } else {
    var upper = atAccent > 0 ? headline.substring(0, atAccent).replace(/\s+$/, "") : "";
    var lower = atAccent >= 0 ? headline.substring(atAccent) : headline;
    if (upper) {
      var upperSize = fittedSize(upper, H*0.085);
      text(comp, "kinetic_title_shadow_top", upper, x+0.005, y-0.071,
        upperSize, [0,0,0], null, start, null);
      text(comp, "kinetic_title_top", upper, x, y-0.08,
        upperSize, [0.91,0.025,0.025], [0.02,0,0], start, null);
    }
    var lowerSize = fittedSize(lower, H*0.115);
    text(comp, "kinetic_title_shadow", lower, x+0.005, y+0.055,
      lowerSize, [0,0,0], null, punch, null);
    var main = text(comp, "kinetic_title_main", lower, x, y+0.047,
      lowerSize, [0.91,0.025,0.025], [0.02,0,0], punch, null);
    punchScale(main);
  }
}
function animatedCaptions(comp) {
  var config = PLAN.caption_animation || {};
  if (!config.enabled) return;
  var cues = config.captions || [];
  for (var i = 0; i < cues.length; i++) {
    var cue = cues[i], preset = String(cue.preset), phrase = String(cue.text);
    var accent = String(cue.accent_text || "");
    var x = Number(cue.position[0]), y = Number(cue.position[1]);
    var start = Number(cue.start_seconds), end = Math.min(DUR - 0.01, Number(cue.end_seconds) + 0.28);
    var size = Math.round(H * (preset == "headline_punch" ? 0.086 : preset == "punctuation_pop" ? 0.077 : 0.065));
    var limit = W * (preset == "floating_dialogue" ? 0.42 : 0.80);
    size = Math.max(26, Math.min(size, Math.floor(limit / Math.max(1, phrase.length * 0.68))));
    var white = [1, 1, 1], red = [0.96, 0.06, 0.04], yellow = [1, 0.9, 0.03];
    var base = preset == "floating_dialogue" ? red : white;
    var accentColor = preset == "headline_punch" ? yellow : red;
    var outline = preset == "floating_dialogue" ? [0.02, 0.01, 0.01] : [0.01, 0.01, 0.02];
    var parts = [], accentIndex = accent ? phrase.indexOf(accent) : -1;
    if (accentIndex >= 0) {
      parts.push({value: phrase.substring(0, accentIndex), color: base, at: start});
      parts.push({value: accent, color: accentColor, at: Number(cue.accent_at_seconds)});
      parts.push({value: phrase.substring(accentIndex + accent.length), color: base, at: start});
    } else {
      parts.push({value: phrase, color: base, at: start});
    }
    var layers = [], total = 0;
    for (var j = 0; j < parts.length; j++) {
      if (!parts[j].value) continue;
      var layer = text(comp, "animated_caption_" + i + "_" + j,
        parts[j].value, x, y, size, parts[j].color, outline, parts[j].at, end);
      var letterStyle = layer.property("Source Text").value;
      try { letterStyle.font = preset == "brush_phrase" ? "HCRBatang-Bold" : "MalgunGothicBold"; }
      catch (fontError) { letterStyle.fauxBold = true; }
      layer.property("Source Text").setValue(letterStyle);
      layer.property("Opacity").setValueAtTime(at(Math.max(parts[j].at, end - 0.10)), 100);
      if (preset == "brush_phrase") layer.property("Rotation").setValue(-2);
      var width = layer.sourceRectAtTime(at(Math.min(DUR - 0.02, start + 0.3)), false).width;
      layers.push({layer: layer, width: width});
      total += width;
    }
    var left = pxX(x) - total / 2;
    for (var k = 0; k < layers.length; k++) {
      var item = layers[k];
      if (preset == "floating_dialogue") {
        item.layer.property("Position").setValueAtTime(at(start), [left + item.width / 2 - 18, pxY(y)]);
        item.layer.property("Position").setValueAtTime(at(start + 0.16), [left + item.width / 2, pxY(y)]);
      } else item.layer.property("Position").setValue([left + item.width / 2, pxY(y)]);
      left += item.width;
    }
    if (preset == "punctuation_pop") {
      var punctuation = text(comp, "animated_caption_punctuation_" + i, "!!!", Math.min(0.88, x + 0.17),
        Math.max(0.12, y - 0.17), Math.round(H * 0.15), red, [0,0,0], start, end);
      var punctuationStyle = punctuation.property("Source Text").value;
      try { punctuationStyle.font = "MalgunGothicBold"; } catch (fontError) { punctuationStyle.fauxBold = true; }
      punctuation.property("Source Text").setValue(punctuationStyle);
      punctuation.property("Opacity").setValueAtTime(at(Math.max(start, end - 0.10)), 100);
    }
  }
}
function animatedSfxText(comp) {
  var config = PLAN.sfx_text_animation || {};
  if (!config.enabled) return;
  var cues = config.cues || [];
  for (var i = 0; i < cues.length; i++) {
    var cue = cues[i], preset = String(cue.preset), phrase = String(cue.text);
    var x = Number(cue.position[0]), y = Number(cue.position[1]);
    var start = Number(cue.start_seconds), end = Math.min(DUR - 0.01, Number(cue.end_seconds));
    var units = Math.max(1, phrase.length);
    var size = Math.max(34, Math.min(Math.round(H * (preset == "sfx_impact" ? 0.15 : 0.12)), Math.floor(W * 0.68 / units)));
    var color = preset == "sfx_emphasis" ? [1,0.88,0.04] : preset == "sfx_whoosh" ? [1,1,1] : [0.98,0.08,0.04];
    var outline = preset == "sfx_whoosh" ? [0.05,0.18,0.55] : [0.015,0.01,0.01];
    var layer = text(comp, "animated_sfx_text_" + i, phrase, x, y, size, color, outline, start, end);
    var style = layer.property("Source Text").value;
    try { style.font = "MalgunGothicBold"; } catch (fontError) { style.fauxBold = true; }
    layer.property("Source Text").setValue(style);
    var scale = layer.property("Scale");
    if (preset == "sfx_impact") {
      scale.setValueAtTime(at(start), [42,42]);
      scale.setValueAtTime(at(start+0.10), [128,128]);
      scale.setValueAtTime(at(start+0.22), [100,100]);
      layer.property("Rotation").setValueAtTime(at(start), -8);
      layer.property("Rotation").setValueAtTime(at(start+0.18), 2);
      layer.property("Rotation").setValueAtTime(at(start+0.30), 0);
    } else if (preset == "sfx_whoosh") {
      layer.property("Position").setValueAtTime(at(start), [pxX(x)-W*0.16, pxY(y)]);
      layer.property("Position").setValueAtTime(at(start+0.20), [pxX(x), pxY(y)]);
      layer.property("Rotation").setValue(-5);
    }
  }
}
function backlitHand(comp) {
  var origin = PLAN.light_origin || [0.5,0.42];
  var cx = Number(origin[0]), cy = Number(origin[1]);
  var raise = firstBeat("hand_raise", 0.15);
  var ignite = firstBeat("light_ignite", raise+0.3);
  var burst = firstBeat("ray_burst", ignite+0.12);
  var afterglow = firstBeat("afterglow", burst+0.65);
  var artRays = layerByRole(comp, "light_rays", false);
  if (artRays) {
    artRays.blendingMode = BlendingMode.ADD;
    setFade(artRays, burst, burst+0.25, null);
    effect(artRays, "ADBE Glo2");
  }
  for (var i = 0; i < 16; i++) {
    var a = 2*Math.PI*i/16;
    var reach = 0.45 + (i%4)*0.08;
    var ray = line(comp, "sun_ray_"+i,
      [[cx+Math.cos(a)*0.025,cy+Math.sin(a)*0.025],
       [cx+Math.cos(a)*reach,cy+Math.sin(a)*reach]],
      [1,0.9,0.64], 4+(i%3)*3, burst+i*0.008, burst+0.45+i*0.008, true);
    ray.property("Opacity").setValueAtTime(at(burst), 0);
    ray.property("Opacity").setValueAtTime(at(burst+0.15), 82);
    ray.property("Opacity").setValueAtTime(at(afterglow), 47);
  }
  var hand = layerByRole(comp, "hand_foreground", true);
  // The foreground hand is composed in full-frame coordinates; light_origin
  // marks the gap between the fingers, not the alpha bounding-box center.
  var target = [W/2,H/2];
  hand.property("Position").setValueAtTime(0, [target[0],target[1]+H*0.14]);
  hand.property("Position").setValueAtTime(at(raise), [target[0],target[1]+H*0.09]);
  hand.property("Position").setValueAtTime(at(ignite), target);
  hand.property("Scale").setValueAtTime(0, [98,98]);
  hand.property("Scale").setValueAtTime(DUR, [105,105]);
  var core = layerByRole(comp, "light_core", false);
  if (!core) core = polygon(comp, "procedural_light_core",
    starPoints(cx,cy,0.065,0.045,20), [1,0.91,0.72], null, 0);
  core.blendingMode = BlendingMode.ADD;
  revealOnBeat(core, ignite);
  core.property("Opacity").setValueAtTime(at(ignite), 0);
  core.property("Opacity").setValueAtTime(at(ignite+0.10), 100);
  core.property("Opacity").setValueAtTime(at(afterglow), 68);
  effect(core, "ADBE Glo2");
  var flash = comp.layers.addSolid([1,0.97,0.87], "sun_flash", W, H, 1, DUR);
  flash.blendingMode = BlendingMode.ADD;
  flash.property("Opacity").setValueAtTime(at(ignite), 0);
  flash.property("Opacity").setValueAtTime(at(ignite+1/FPS), 42);
  flash.property("Opacity").setValueAtTime(at(ignite+0.35), 0);
  var beats = PLAN.beats || [];
  for (var j = 0; j < beats.length; j++) {
    if (beats[j].action == "caption" && beats[j].text) {
      text(comp, "backlit_caption", beats[j].text, 0.5, 0.89,
        Math.round(H*0.062), [1,1,1], [0,0,0], Number(beats[j].at_seconds), null);
    }
  }
}
function directedPerformance(comp) {
  var requirements = PLAN.asset_requirements || {};
  var required = requirements.required_layers || [];
  var poses = [];
  for (var i = 0; i < required.length; i++) {
    var role = String(required[i]);
    if (role == "background") continue;
    var layer = layerByRole(comp, role, true);
    layer.property("Opacity").setValue(0);
    if (role.indexOf("pose_") === 0) poses.push({role: role, layer: layer});
    if (role == "blanket" || role == "shoji" || role == "character") {
      layer.property("Opacity").setValue(100);
    }
  }
  var beats = PLAN.beats || [];
  var activePose = null;
  var fadeFrames = Math.max(2 / FPS, Number(PLAN.pose_crossfade_seconds || 0.14));
  for (var b = 0; b < beats.length; b++) {
    var beat = beats[b], when = at(beat.at_seconds), action = String(beat.action);
    var target = String(beat.target || "");
    if (action == "pose_reveal") {
      var next = null;
      for (var p = 0; p < poses.length; p++) if (poses[p].role == target) next = poses[p].layer;
      if (!next) throw "pose_reveal target is not an approved pose layer: " + target;
      if (activePose) {
        activePose.property("Opacity").setValueAtTime(Math.max(0, when - 1/FPS), 100);
        activePose.property("Opacity").setValueAtTime(at(when + fadeFrames), 0);
      }
      next.property("Opacity").setValueAtTime(Math.max(0, when - 1/FPS), 0);
      next.property("Opacity").setValueAtTime(when, 0);
      next.property("Opacity").setValueAtTime(at(when + fadeFrames), 100);
      activePose = next;
    } else if (action == "prop_reveal" || action == "mask_reveal") {
      var prop = layerByRole(comp, target, true);
      prop.property("Opacity").setValueAtTime(Math.max(0, when - 1/FPS), 0);
      prop.property("Opacity").setValueAtTime(when, 100);
    }
    var focus = beat.attention_target;
    if (focus && focus.length == 2) {
      var cue = comp.layers.addShape();
      cue.name = "directorial_attention_" + b;
      var cueGroup = cue.property("Contents").addProperty("ADBE Vector Group");
      var cueContents = cueGroup.property("Contents");
      var cueEllipse = cueContents.addProperty("ADBE Vector Shape - Ellipse");
      cueEllipse.property("Size").setValue([190,190]);
      var cueFill = cueContents.addProperty("ADBE Vector Graphic - Fill");
      cueFill.property("Color").setValue([0.88,0.72,0.48]);
      cue.property("Position").setValue([pxX(focus[0]),pxY(focus[1])]);
      cue.blendingMode = BlendingMode.ADD;
      try { cue.property("Effects").addProperty("ADBE Glo2"); } catch (focusError) {}
      cue.property("Opacity").setValueAtTime(when, 0);
      cue.property("Opacity").setValueAtTime(at(when + 0.18), 16);
      cue.property("Opacity").setValueAtTime(at(Math.min(DUR, Number(beat.end_seconds || when + 0.8))), 0);
    }
  }
  if (poses.length && !activePose) {
    poses[0].layer.property("Opacity").setValueAtTime(0, 100);
  }
}
var SOURCES = {};
app.beginSuppressDialogs();
try {
  if (app.project) app.project.close(CloseOptions.DO_NOT_SAVE_CHANGES);
  app.newProject();
  var options = new ImportOptions(new File(CFG.source));
  if (!options.canImportAs(ImportAsType.COMP)) throw "PSD cannot import as composition";
  options.importAs = ImportAsType.COMP;
  var imported = app.project.importFile(options);
  if (!(imported instanceof CompItem)) throw "Layered PSD was not imported as composition";
  for (var li = 1; li <= imported.numLayers; li++) {
    var sourceLayer = imported.layer(li);
    SOURCES[String(sourceLayer.name).toLowerCase()] = sourceLayer;
  }
  var comp = app.project.items.addComp(CFG.comp, W, H, 1, DUR, FPS);
  comp.bgColor = [0.03,0.02,0.05];
  var bg = layerByRole(comp, "background", true);
  bg.moveToEnd();
  // Directed performance uses authored pose changes and story attention cues.
  // Keep the plate locked; a continuous scale-up is not a substitute for direction.
  bg.property("Scale").setValue([100,100]);
  if (CFG.template == "parallax_layered_scene") parallaxLayeredScene(comp);
  else if (CFG.template == "dialogue_closeup") dialogueCloseup(comp);
  else if (CFG.template == "angled_triple_reaction") triple(comp);
  else if (CFG.template == "body_following_qi") qi(comp);
  else if (CFG.template == "ink_splat_impact") impact(comp);
  else if (CFG.template == "wall_impact_debris") wallImpact(comp);
  else if (CFG.template == "glasses_reflection") glassesReflection(comp);
  else if (CFG.template == "kinetic_title_reveal") kineticTitle(comp);
  else if (CFG.template == "backlit_hand_reveal") backlitHand(comp);
  else if (CFG.template == "directed_performance") directedPerformance(comp);
  else throw "Unknown manga template: " + CFG.template;
  animatedCaptions(comp);
  animatedSfxText(comp);
  var rq = app.project.renderQueue.items.add(comp);
  rq.outputModule(1).file = new File(CFG.render);
  app.project.save(new File(CFG.project));
  if (!new File(CFG.project).exists) throw new Error("Project save returned without creating AEP: " + CFG.project);
  var success = new File(CFG.status);
  if (success.open("w")) { success.write("success|" + CFG.project + "|" + CFG.template + "|" + imported.numLayers); success.close(); }
  app.scheduleTask("app.quit()", 1200, false);
} catch (error) {
  var failure = new File(CFG.status);
  if (failure.open("w")) { failure.write("error|" + error.toString() + "|line=" + error.line); failure.close(); }
  app.scheduleTask("app.quit()", 1200, false);
  throw error;
} finally {
  app.endSuppressDialogs(false);
}
'''
