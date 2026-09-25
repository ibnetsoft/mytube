var psdPath = "D:/Projects/에어스튜디오/mytube_clone_20260828/ae_layer_tests/source.psd";
var reportPath = "D:/Projects/에어스튜디오/mytube_clone_20260828/ae_layer_tests/layer_report.txt";
var projectPath = "D:/Projects/에어스튜디오/mytube_clone_20260828/ae_layer_tests/layer_import_test.aep";

function writeReport(lines) {
  var out = new File(reportPath);
  out.encoding = "UTF-8";
  out.open("w");
  for (var i = 0; i < lines.length; i++) {
    out.writeln(lines[i]);
  }
  out.close();
}

var lines = [];
app.beginSuppressDialogs();

try {
  if (app.project) {
    app.project.close(CloseOptions.DO_NOT_SAVE_CHANGES);
  }
  app.newProject();

  var psd = new File(psdPath);
  if (!psd.exists) {
    throw new Error("PSD not found: " + psdPath);
  }

  var options = new ImportOptions(psd);
  options.importAs = ImportAsType.COMP_CROPPED_LAYERS;
  var imported = app.project.importFile(options);

  lines.push("imported_name=" + imported.name);
  lines.push("imported_type=" + imported.typeName);
  lines.push("comp_width=" + imported.width);
  lines.push("comp_height=" + imported.height);
  lines.push("comp_duration=" + imported.duration);
  lines.push("layer_count=" + imported.numLayers);

  for (var i = 1; i <= imported.numLayers; i++) {
    var layer = imported.layer(i);
    var sourceName = layer.source ? layer.source.name : "";
    var sourceSize = layer.source ? (layer.source.width + "x" + layer.source.height) : "";
    lines.push(i + "\tname=" + layer.name + "\tsource=" + sourceName + "\tsize=" + sourceSize + "\tstart=" + layer.startTime + "\tin=" + layer.inPoint + "\tout=" + layer.outPoint);
  }

  app.project.save(new File(projectPath));
  lines.push("project_saved=" + projectPath);
} catch (err) {
  lines.push("ERROR=" + err.toString());
} finally {
  writeReport(lines);
  app.endSuppressDialogs(false);
}
