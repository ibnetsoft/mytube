var projectPath = "D:/Projects/에어스튜디오/mytube_clone_20260828/ae_wuxia_fx/wuxia_ae_fx.aep";
var previewPath = "D:/Projects/에어스튜디오/mytube_clone_20260828/ae_wuxia_fx/wuxia_ae_fx_preview_2s.png";

app.beginSuppressDialogs();
try {
  app.open(new File(projectPath));
  var comp = app.project.item(1);
  for (var i = 1; i <= app.project.numItems; i++) {
    if (app.project.item(i).name == "wuxia_sword_aura_AE_only_fx") {
      comp = app.project.item(i);
      break;
    }
  }
  comp.saveFrameToPng(2.0, new File(previewPath));
} finally {
  app.endSuppressDialogs(false);
}
