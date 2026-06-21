import os
import re

filepath = 'templates/pages/image_crop.html'
with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

old_block = '''    const isVi = (window.currentLang === 'vi');
    const i18nCrop = {
        pageDesc: isVi ? "Tải lên cùng lúc nhiều ảnh lưới 2x2 để cắt hàng loạt và tải xuống tất cả các ảnh đã cắt trong một lần." : "2x2 격자판 이미지를 일괄 업로드하여 한 번에 자르고, 잘린 개별 이미지를 모두 다운로드 할 수 있습니다.",
        dragDropDesc: isVi ? "Kéo và thả hoặc nhấp để chọn nhiều tệp" : "마우스로 드래그하거나 클릭하여 다중 선택",
        listTitle: isVi ? "Danh sách tệp đã tải lên" : "업로드된 파일 목록",
        clearAll: isVi ? "Xóa tất cả" : "전체 삭제",
        cropAllBtn: isVi ? "Cắt tất cả các tệp cùng lúc" : "⚡ 목록의 모든 파일 자르기",
        batchResultTitle: isVi ? "Kết quả cắt hàng loạt" : "일괄 자르기 결과물",
        batchResultDesc: isVi ? "Vui lòng tải ảnh lưới ở phía bên trái và nhấp vào nút cắt." : "좌측에 격자 이미지를 추가하고 자르기 버튼을 눌러주세요.",
        previewSelected: isVi ? "Xem trước tệp đã chọn" : "선택된 파일 미리보기",
        rawGridBadge: isVi ? "Ảnh gốc 2x2" : "2x2 원본",
        batchResultHeading: isVi ? "Danh sách kết quả cắt ảnh" : "잘려진 개별 이미지 결과",
        downloadZipBtn: isVi ? "Tải xuống tất cả (.zip)" : "전체 결과 다운로드 (.zip)",
        processing: isVi ? "Đang cắt toàn bộ tệp..." : "전체 파일 자르는 중...",
        panelDone: isVi ? "Cắt xong 4 ô ảnh" : "4개 패널 자르기 완료",
        download: isVi ? "Tải xuống" : "다운로드",
        successToast: isVi ? "Đã cắt hàng loạt toàn bộ ảnh thành công!" : "모든 이미지 일괄 자르기가 완료되었습니다!",
        errorToast: isVi ? "Lỗi khi cắt hàng loạt: " : "일괄 자르기 중 오류 발생: ",
        zipProcessing: isVi ? "Đang tạo tệp nén (.zip)..." : "압축(.zip) 파일 생성 중...",
        zipSuccess: isVi ? "Tải xuống hàng loạt hoàn tất!" : "일괄 다운로드가 시작되었습니다!"
    };'''

new_block = '''    const isVi = (window.currentLang === 'vi');
    const isEn = (window.currentLang === 'en');
    const t = (ko, en, vi) => isVi ? vi : (isEn ? en : ko);
    
    const i18nCrop = {
        pageDesc: t("2x2 격자판 이미지를 일괄 업로드하여 한 번에 자르고, 잘린 개별 이미지를 모두 다운로드 할 수 있습니다.", "Batch upload 2x2 grid images to crop all at once and download the separated images.", "Tải lên cùng lúc nhiều ảnh lưới 2x2 để cắt hàng loạt và tải xuống tất cả các ảnh đã cắt trong một lần."),
        dragDropDesc: t("마우스로 드래그하거나 클릭하여 다중 선택", "Drag and drop or click to select multiple files", "Kéo và thả hoặc nhấp để chọn nhiều tệp"),
        listTitle: t("업로드된 파일 목록", "Uploaded File List", "Danh sách tệp đã tải lên"),
        clearAll: t("전체 삭제", "Clear All", "Xóa tất cả"),
        cropAllBtn: t("⚡ 목록의 모든 파일 자르기", "⚡ Crop All Files", "Cắt tất cả các tệp cùng lúc"),
        batchResultTitle: t("일괄 자르기 결과물", "Batch Crop Results", "Kết quả cắt hàng loạt"),
        batchResultDesc: t("좌측에 격자 이미지를 추가하고 자르기 버튼을 눌러주세요.", "Please add a grid image on the left and click crop.", "Vui lòng tải ảnh lưới ở phía bên trái và nhấp vào nút cắt."),
        previewSelected: t("선택된 파일 미리보기", "Preview Selected File", "Xem trước tệp đã chọn"),
        rawGridBadge: t("2x2 원본", "2x2 Original", "Ảnh gốc 2x2"),
        batchResultHeading: t("잘려진 개별 이미지 결과", "Cropped Image Results", "Danh sách kết quả cắt ảnh"),
        downloadZipBtn: t("전체 결과 다운로드 (.zip)", "Download All (.zip)", "Tải xuống tất cả (.zip)"),
        processing: t("전체 파일 자르는 중...", "Processing all files...", "Đang cắt toàn bộ tệp..."),
        panelDone: t("4개 패널 자르기 완료", "4 Panels Cropped", "Cắt xong 4 ô ảnh"),
        download: t("다운로드", "Download", "Tải xuống"),
        successToast: t("모든 이미지 일괄 자르기가 완료되었습니다!", "All images batch cropped successfully!", "Đã cắt hàng loạt toàn bộ ảnh thành công!"),
        errorToast: t("일괄 자르기 중 오류 발생: ", "Error during batch crop: ", "Lỗi khi cắt hàng loạt: "),
        zipProcessing: t("압축(.zip) 파일 생성 중...", "Creating .zip file...", "Đang tạo tệp nén (.zip)..."),
        zipSuccess: t("일괄 다운로드가 시작되었습니다!", "Batch download started!", "Tải xuống hàng loạt hoàn tất!")
    };'''

if old_block in content:
    content = content.replace(old_block, new_block)
    
    old_panel_labels = '''    const panelLabels = isVi 
        ? ['Trên bên trái (P1)', 'Trên bên phải (P2)', 'Dưới bên trái (P3)', 'Dưới bên phải (P4)'] 
        : ['좌측 상단 (P1)', '우측 상단 (P2)', '좌측 하단 (P3)', '우측 하단 (P4)'];'''
        
    new_panel_labels = '''    const panelLabels = isVi 
        ? ['Trên bên trái (P1)', 'Trên bên phải (P2)', 'Dưới bên trái (P3)', 'Dưới bên phải (P4)'] 
        : isEn ? ['Top Left (P1)', 'Top Right (P2)', 'Bottom Left (P3)', 'Bottom Right (P4)']
        : ['좌측 상단 (P1)', '우측 상단 (P2)', '좌측 하단 (P3)', '우측 하단 (P4)'];'''
        
    content = content.replace(old_panel_labels, new_panel_labels)

    old_raw_name = '''        const rawName = isVi ? `${i18nCrop.previewSelected}: ${file.name}` : file.name;'''
    new_raw_name = '''        const rawName = (isVi || isEn) ? `${i18nCrop.previewSelected}: ${file.name}` : file.name;'''
    content = content.replace(old_raw_name, new_raw_name)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Fixed image_crop.html")
else:
    print("Could not find old block in image_crop.html")
