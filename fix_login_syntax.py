import re

with open('templates/pages/login.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix the syntax error and replace keys
content = content.replace("lbl_remember_me: \\'아이디/비밀번호 저장\\',", "lbl_remember_email: '아이디 저장', lbl_remember_password: '비밀번호 저장',")
content = content.replace("lbl_remember_me: \\'จดจำการเข้าสู่ระบบ\\',", "lbl_remember_email: 'จดจำอีเมล', lbl_remember_password: 'จดจำรหัสผ่าน',")
content = content.replace("lbl_remember_me: \\'Remember me\\',", "lbl_remember_email: 'Remember Email', lbl_remember_password: 'Remember Password',")
content = content.replace("lbl_remember_me: \\'Ghi nhớ đăng nhập\\',", "lbl_remember_email: 'Ghi nhớ Email', lbl_remember_password: 'Ghi nhớ mật khẩu',")

with open('templates/pages/login.html', 'w', encoding='utf-8') as f:
    f.write(content)
