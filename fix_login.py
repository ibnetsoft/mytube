import re

with open('templates/pages/login.html', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Replace the checkbox HTML
old_checkbox = """<div class="flex items-center gap-2 px-1">
                    <input type="checkbox" id="remember-me" class="w-4 h-4 rounded border-white/20 bg-white/5 text-blue-500 focus:ring-blue-500 focus:ring-offset-gray-900 cursor-pointer">
                    <label for="remember-me" class="text-xs text-gray-400 cursor-pointer select-none" data-i18n="lbl_remember_me">아이디/비밀번호 저장</label>
                </div>"""

new_checkboxes = """<div class="flex items-center gap-4 px-1">
                    <div class="flex items-center gap-1.5">
                        <input type="checkbox" id="remember-email" class="w-4 h-4 rounded border-white/20 bg-white/5 text-blue-500 focus:ring-blue-500 focus:ring-offset-gray-900 cursor-pointer">
                        <label for="remember-email" class="text-xs text-gray-400 cursor-pointer select-none" data-i18n="lbl_remember_email">아이디 저장</label>
                    </div>
                    <div class="flex items-center gap-1.5">
                        <input type="checkbox" id="remember-password" class="w-4 h-4 rounded border-white/20 bg-white/5 text-blue-500 focus:ring-blue-500 focus:ring-offset-gray-900 cursor-pointer">
                        <label for="remember-password" class="text-xs text-gray-400 cursor-pointer select-none" data-i18n="lbl_remember_password">비밀번호 저장</label>
                    </div>
                </div>"""
content = content.replace(old_checkbox, new_checkboxes)

# 2. Add translation keys
content = re.sub(r'lbl_remember_me: \'아이디/비밀번호 저장\',', r'lbl_remember_email: \'아이디 저장\', lbl_remember_password: \'비밀번호 저장\',', content)
content = re.sub(r'lbl_remember_me: \'จดจำการเข้าสู่ระบบ\',', r'lbl_remember_email: \'จดจำอีเมล\', lbl_remember_password: \'จดจำรหัสผ่าน\',', content)
content = re.sub(r'lbl_remember_me: \'Remember me\',', r'lbl_remember_email: \'Remember Email\', lbl_remember_password: \'Remember Password\',', content)
content = re.sub(r'lbl_remember_me: \'Ghi nhớ đăng nhập\',', r'lbl_remember_email: \'Ghi nhớ Email\', lbl_remember_password: \'Ghi nhớ mật khẩu\',', content)

# 3. Update DOMContentLoaded
old_dom = """        const savedEmail = localStorage.getItem('remembered_email');
        const savedPassword = localStorage.getItem('remembered_password');
        if (savedEmail && savedPassword) {
            document.getElementById('login-email').value = savedEmail;
            document.getElementById('login-password').value = savedPassword;
            document.getElementById('remember-me').checked = true;
            checkLoginBtn();
        }"""

new_dom = """        const savedEmail = localStorage.getItem('remembered_email');
        const savedPassword = localStorage.getItem('remembered_password');
        if (savedEmail) {
            document.getElementById('login-email').value = savedEmail;
            document.getElementById('remember-email').checked = true;
        }
        if (savedPassword) {
            document.getElementById('login-password').value = savedPassword;
            document.getElementById('remember-password').checked = true;
        }
        setTimeout(() => { checkLoginBtn(); }, 50);
        setTimeout(() => { checkLoginBtn(); }, 300);"""
content = content.replace(old_dom, new_dom)

# 4. Update submitLogin
old_submit = """                if (document.getElementById('remember-me').checked) {
                    localStorage.setItem('remembered_email', email);
                    localStorage.setItem('remembered_password', password);
                } else {
                    localStorage.removeItem('remembered_email');
                    localStorage.removeItem('remembered_password');
                }"""

new_submit = """                if (document.getElementById('remember-email').checked) {
                    localStorage.setItem('remembered_email', email);
                } else {
                    localStorage.removeItem('remembered_email');
                }
                if (document.getElementById('remember-password').checked) {
                    localStorage.setItem('remembered_password', password);
                } else {
                    localStorage.removeItem('remembered_password');
                }"""
content = content.replace(old_submit, new_submit)

with open('templates/pages/login.html', 'w', encoding='utf-8') as f:
    f.write(content)
