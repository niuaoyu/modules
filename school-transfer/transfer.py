"""校园网临时互传工具；仅使用 Python 标准库。"""
import argparse
import getpass
import hashlib
import hmac
import json
import mimetypes
import os
import secrets
import socket
import tempfile
import threading
import time
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

MAX_UPLOAD = 1024 * 1024 * 1024
MAX_NOTE = 100_000
MAX_UPLOAD_LABEL = '1 GB'
SESSION_AGE = 12 * 3600
HTML = r'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>校园网互传</title><style>body{font:15px/1.6 system-ui,sans-serif;max-width:760px;margin:35px auto;padding:0 18px;color:#203047;background:#f5f8fb}main{background:white;padding:24px;border:1px solid #dbe4ed;border-radius:14px}h1{font-size:24px;margin:0 0 8px}h2{font-size:17px;margin:24px 0 8px}input,textarea,button{font:inherit;box-sizing:border-box}input:not([type=file]),textarea{width:100%;padding:10px;border:1px solid #acbdcd;border-radius:8px}textarea{min-height:105px}button{background:#185fa5;color:white;border:0;border-radius:8px;padding:9px 16px;cursor:pointer}button.secondary{background:#e6f1fb;color:#185fa5}button.danger{background:#fcebeb;color:#a32d2d}p.tip{color:#5f6b78;font-size:13px}label{display:block;margin:12px 0 5px}li{padding:10px;border-bottom:1px solid #e6edf3;word-break:break-all}li a{margin-left:8px}small{color:#657685}#message{min-height:24px;color:#a32d2d}img{max-height:110px;max-width:180px;display:block}#app{display:none}</style><main><h1>校园网互传</h1><p class="tip">文字、截图和文件暂存到服务所在电脑。仅在可信网络中使用；HTTP 不加密。</p><section id="login"><label>用户名</label><input id="user" value="nay" autocomplete="username"><label>密码</label><input id="pass" type="password" autocomplete="current-password"><p><button onclick="login()">登录</button></p></section><section id="app"><p><button class="secondary" onclick="logout()">退出登录</button></p><h2>发送文字</h2><textarea id="note" placeholder="粘贴文字或链接"></textarea><p><button onclick="sendNote()">发送文字</button></p><h2>发送图片或文件</h2><p class="tip">支持 Ctrl+V 粘贴截图、一次选择多个文件；单个文件最大 1 GB。</p><input id="file" type="file" multiple><p><button onclick="sendFiles()">上传选中文件</button></p><h2>最近内容</h2><button class="secondary" onclick="refresh()">刷新</button><ul id="list"></ul></section><p id="message" role="status"></p></main><script>
let csrf=''; const $=id=>document.getElementById(id);
function msg(t){$('message').textContent=t}
async function request(path,opts={}){let headers={...(opts.headers||{})};if(csrf)headers['X-CSRF-Token']=csrf;let r=await fetch(path,{credentials:'same-origin',...opts,headers});let j=await r.json();if(!r.ok)throw Error(j.error||'请求失败');return j}
async function check(){try{let j=await request('/api/me');csrf=j.csrf;$('login').style.display='none';$('app').style.display='block';await refresh()}catch{ $('login').style.display='block';$('app').style.display='none'}}
async function login(){try{let j=await request('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({user:$('user').value,password:$('pass').value})});csrf=j.csrf;$('pass').value='';msg('登录成功');await check()}catch(e){msg(e.message)}}
async function logout(){try{await request('/api/logout',{method:'POST'})}catch{}csrf='';await check()}
async function sendNote(){let text=$('note').value.trim();if(!text)return msg('请先输入文字');try{await request('/api/note',{method:'POST',headers:{'Content-Type':'text/plain;charset=utf-8'},body:text});$('note').value='';msg('文字已发送');await refresh()}catch(e){msg(e.message)}}
async function sendFile(file){if(!(file instanceof File))return sendFiles();if(file.size>1024*1024*1024)return msg('单个文件不能超过 1 GB');try{await request('/api/upload?name='+encodeURIComponent(file.name),{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:file});msg(file.name+' 上传成功');await refresh()}catch(e){msg(file.name+'：'+e.message)}}
  async function sendFiles(){let files=[...$('file').files];if(!files.length)return msg('请先选择文件');if(files.some(f=>f.size>1024*1024*1024))return msg('单个文件不能超过 1 GB');let success=0;for(let i=0;i<files.length;i++){msg('正在上传 '+(i+1)+'/'+files.length+'：'+files[i].name);try{await request('/api/upload?name='+encodeURIComponent(files[i].name),{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:files[i]});success++}catch(e){msg(files[i].name+'：'+e.message)}}$('file').value='';msg('已上传 '+success+'/'+files.length+' 个文件');await refresh()}
  async function copyText(text){try{if(navigator.clipboard&&typeof navigator.clipboard.writeText==='function'){await navigator.clipboard.writeText(text);return true}}catch(e){}let ta=document.createElement('textarea');ta.value=text;ta.style.position='fixed';ta.style.opacity='0';document.body.appendChild(ta);ta.focus();ta.select();let ok=false;try{ok=document.execCommand('copy')}catch(e){}ta.remove();return ok}
  async function refresh(){try{let j=await request('/api/list');let ul=$('list');ul.replaceChildren();for(let item of j.items){let li=document.createElement('li');let title=document.createElement('span');title.textContent=item.name+' · '+(item.size/1024).toFixed(1)+' KB';li.append(title);let a=document.createElement('a');a.href='/api/download/'+encodeURIComponent(item.id);a.textContent='下载';li.append(a);if(item.name.endsWith('.txt')){let copy=document.createElement('button');copy.className='secondary';copy.textContent='复制文字';copy.onclick=async()=>{try{let r=await fetch(a.href,{credentials:'same-origin'});if(!r.ok)throw Error('读取失败');let ok=await copyText(await r.text());msg(ok?'已复制到剪贴板':'浏览器禁止剪贴板操作，请使用下载按钮后复制')}catch(e){msg(e.message)}};li.append(' ',copy)}let del=document.createElement('button');del.className='danger';del.textContent='删除';del.onclick=async()=>{if(!confirm('删除这个文件？'))return;try{await request('/api/delete/'+encodeURIComponent(item.id),{method:'POST'});await refresh()}catch(e){msg(e.message)}};li.append(' ',del);ul.append(li)}}catch(e){msg(e.message)}}
document.addEventListener('paste',e=>{if($('app').style.display==='none')return;for(let item of e.clipboardData?.items||[])if(item.type.startsWith('image/')){let file=item.getAsFile();if(file){e.preventDefault();sendFile(new File([file],'截图-'+new Date().toISOString().replace(/[:.]/g,'-')+'.png',{type:file.type}));break}}});check();
</script></html>'''


def make_handler(root, username, salt, password_hash):
    sessions = {}
    lock = threading.Lock()
    attempts = {}

    class Handler(BaseHTTPRequestHandler):
        server_version = 'CampusTransfer/1.0'

        def reply(self, code, payload, cookie=None):
            data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
            self.send_response(code)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'unsafe-inline' 'self'; script-src 'unsafe-inline' 'self'")
            if cookie:
                self.send_header('Set-Cookie', cookie)
            self.end_headers()
            self.wfile.write(data)

        def auth(self, changing=False):
            jar = SimpleCookie()
            try:
                jar.load(self.headers.get('Cookie', ''))
                token = jar['sid'].value if 'sid' in jar else ''
            except Exception:
                token = ''
            with lock:
                entry = sessions.get(token)
                if entry and entry[1] < time.time():
                    sessions.pop(token, None)
                    entry = None
            if not entry:
                self.reply(401, {'error': '请先登录'})
                return None
            if changing and not hmac.compare_digest(self.headers.get('X-CSRF-Token', ''), entry[0]):
                self.reply(403, {'error': '请求校验失败，请重新登录'})
                return None
            return token, entry[0]

        def body(self, limit):
            try:
                size = int(self.headers.get('Content-Length', '-1'))
            except ValueError:
                size = -1
            if size < 0 or size > limit:
                self.reply(413, {'error': '请求过大或缺少内容长度'})
                return None
            return self.rfile.read(size)

        def get_path(self, path):
            file_id = unquote(path.rsplit('/', 1)[-1])
            if not file_id or '/' in file_id or '\\' in file_id or file_id in {'.', '..'}:
                return None
            file = root / file_id
            return file if file.is_file() else None

        def do_GET(self):
            path = urlsplit(self.path).path
            if path == '/':
                content = HTML.encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(content)))
                self.send_header('Cache-Control', 'no-store')
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.end_headers()
                self.wfile.write(content)
                return
            auth = self.auth()
            if not auth:
                return
            if path == '/api/me':
                return self.reply(200, {'csrf': auth[1]})
            if path == '/api/list':
                files = sorted((f for f in root.iterdir() if f.is_file() and not f.is_symlink()), key=lambda f: f.stat().st_mtime, reverse=True)
                return self.reply(200, {'items': [{'id': f.name, 'name': f.name.split('-', 2)[-1], 'size': f.stat().st_size} for f in files[:200]]})
            if path.startswith('/api/download/'):
                file = self.get_path(path)
                if not file:
                    return self.reply(404, {'error': '文件不存在'})
                self.send_response(200)
                self.send_header('Content-Type', 'application/octet-stream')
                self.send_header('Content-Disposition', "attachment; filename*=UTF-8''" + quote(file.name.split('-', 2)[-1]))
                self.send_header('Content-Length', str(file.stat().st_size))
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.end_headers()
                with file.open('rb') as f:
                    while chunk := f.read(65536):
                        self.wfile.write(chunk)
                return
            self.reply(404, {'error': '路径不存在'})

        def do_POST(self):
            path = urlsplit(self.path).path
            if path == '/api/login':
                ip = self.client_address[0]
                with lock:
                    stamps = [t for t in attempts.get(ip, []) if t > time.time() - 60]
                    attempts[ip] = stamps
                    blocked = len(stamps) >= 8
                if blocked:
                    return self.reply(429, {'error': '登录尝试过多，请一分钟后重试'})
                body = self.body(4096)
                if body is None:
                    return
                try:
                    data = json.loads(body)
                    user, password = str(data['user']), str(data['password'])
                except (ValueError, KeyError, TypeError):
                    return self.reply(400, {'error': '登录数据无效'})
                candidate = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 200_000)
                if not (hmac.compare_digest(user, username) and hmac.compare_digest(candidate, password_hash)):
                    with lock:
                        attempts[ip].append(time.time())
                    return self.reply(401, {'error': '用户名或密码错误'})
                token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
                with lock:
                    attempts.pop(ip, None)
                    sessions[token] = (csrf, time.time() + SESSION_AGE)
                return self.reply(200, {'csrf': csrf}, f'sid={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age={SESSION_AGE}')
            auth = self.auth(changing=True)
            if not auth:
                return
            if path == '/api/logout':
                with lock:
                    sessions.pop(auth[0], None)
                return self.reply(200, {'ok': True}, 'sid=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0')
            if path == '/api/note':
                body = self.body(MAX_NOTE)
                if body is None:
                    return
                try:
                    text = body.decode('utf-8')
                except UnicodeDecodeError:
                    return self.reply(400, {'error': '文字编码必须为 UTF-8'})
                if not text.strip():
                    return self.reply(400, {'error': '文字不能为空'})
                name = time.strftime('%Y%m%d-%H%M%S') + '-' + secrets.token_hex(4) + '-文字.txt'
                (root / name).write_text(text, encoding='utf-8')
                return self.reply(201, {'ok': True})
            if path == '/api/upload':
                try:
                    size = int(self.headers.get('Content-Length', '-1'))
                except ValueError:
                    size = -1
                if size < 0 or size > MAX_UPLOAD:
                    return self.reply(413, {'error': '单个文件不能超过 1 GB，且请求必须包含文件大小'})
                from urllib.parse import parse_qs
                name = parse_qs(urlsplit(self.path).query).get('name', ['文件'])[0]
                name = name.replace('\\', '/').split('/')[-1].strip().strip('.')[:90]
                if not name or name in {'.', '..'}:
                    return self.reply(400, {'error': '文件名无效'})
                name = ''.join(c for c in name if c.isprintable() and c not in '<>:"/\\|?*') or '文件'
                name = time.strftime('%Y%m%d-%H%M%S') + '-' + secrets.token_hex(4) + '-' + name
                target = root / name
                written = 0
                try:
                    with target.open('xb') as f:
                        while written < size:
                            chunk = self.rfile.read(min(1024 * 1024, size - written))
                            if not chunk:
                                raise ConnectionError('上传中断')
                            f.write(chunk)
                            written += len(chunk)
                except Exception:
                    target.unlink(missing_ok=True)
                    raise
                return self.reply(201, {'ok': True})
            if path.startswith('/api/delete/'):
                file = self.get_path(path)
                if not file:
                    return self.reply(404, {'error': '文件不存在'})
                file.unlink()
                return self.reply(200, {'ok': True})
            self.reply(404, {'error': '路径不存在'})

    return Handler


def main():
    parser = argparse.ArgumentParser(description='校园网文字/图片/文件互传')
    parser.add_argument('--host', default='127.0.0.1', help='监听地址：局域网使用 0.0.0.0')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--dir', default='transfer_inbox', help='文件保存目录')
    parser.add_argument('--user', default='nay', help='互传页面用户名')
    args = parser.parse_args()
    password = os.environ.get('TRANSFER_PASSWORD') or getpass.getpass('互传页面密码（输入不显示）: ')
    if not password:
        parser.error('密码不能为空')
    root = Path(args.dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    salt = secrets.token_bytes(16)
    pwd_hash = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 200_000)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(root, args.user, salt, pwd_hash))
    print(f'互传服务已启动：http://{args.host}:{args.port}，文件目录：{root}', flush=True)
    if args.host != '127.0.0.1':
        print('提示：HTTP 不加密；请仅在可信网络中临时开启，结束后按 Ctrl+C 停止。', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\n服务已停止')
    finally:
        server.server_close()


if __name__ == '__main__':
    main()