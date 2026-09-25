var imagePath = "C:/Users/Pc/AppData/Local/Temp/codex-clipboard-21c49015-f5ef-4734-8bf0-f8c996c781f2.png";
var projectPath = "D:/Projects/에어스튜디오/mytube_clone_20260828/ae_test/codex_image_test.aep";
var renderPath = "D:/Projects/에어스튜디오/mytube_clone_20260828/ae_test/codex_image_test.avi";

app.beginUndoGroup("Codex PNG render test");

if (app.project) {
  app.project.close(CloseOptions.DO_NOT_SAVE_CHANGES);
}

app.newProject();

var pngFile = new File(imagePath);
if (!pngFile.exists) {
  throw new Error("PNG source was not found: " + imagePath);
}

var importOptions = new ImportOptions(pngFile);
var footage = app.project.importFile(importOptions);

var comp = app.project.items.addComp("codex_png_3sec_test", 640, 480, 1, 3, 24);
comp.bgColor = [0.02, 0.03, 0.08];

var layer = comp.layers.add(footage);
layer.name = "source_png_motion_test";

var sourceScale = Math.min(comp.width / footage.width, comp.height / footage.height) * 100;
layer.property("Scale").setValueAtTime(0, [sourceScale, sourceScale]);
layer.property("Scale").setValueAtTime(3, [sourceScale * 1.08, sourceScale * 1.08]);
layer.property("Position").setValueAtTime(0, [comp.width / 2 - 8, comp.height / 2 + 6]);
layer.property("Position").setValueAtTime(1.5, [comp.width / 2 + 10, comp.height / 2 - 4]);
layer.property("Position").setValueAtTime(3, [comp.width / 2, comp.height / 2]);

var textLayer = comp.layers.addText("AE CS6 render test");
textLayer.name = "render_status_label";
textLayer.property("Position").setValue([18, 455]);
var textDocument = textLayer.property("Source Text").value;
textDocument.fontSize = 24;
textDocument.fillColor = [1, 1, 1];
textDocument.applyFill = true;
textLayer.property("Source Text").setValue(textDocument);

var rqItem = app.project.renderQueue.items.add(comp);
rqItem.outputModule(1).file = new File(renderPath);

app.project.save(new File(projectPath));

app.endUndoGroup();
