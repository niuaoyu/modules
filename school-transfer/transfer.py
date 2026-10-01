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
import shutil
import tempfile
import threading
import zipfile
import time
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

MAX_UPLOAD = 1024 * 1024 * 1024
MAX_NOTE = 100_000
MAX_UPLOAD_LABEL = '1 GB'
MAX_BATCH_FILES = 500
SESSION_AGE = 12 * 3600
HTML = r'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>校园网互传</title><style>body{font:15px/1.6 system-ui,sans-serif;max-width:760px;margin:35px auto;padding:0 18px;color:#203047;background:#f5f8fb}main{background:white;padding:24px;border:1px solid #dbe4ed;border-radius:14px}h1{font-size:24px;margin:0 0 8px}h2{font-size:17px;margin:24px 0 8px}input,textarea,button{font:inherit;box-sizing:border-box}input:not([type=file]),textarea{width:100%;padding:10px;border:1px solid #acbdcd;border-radius:8px}textarea{min-height:105px}button{background:#185fa5;color:white;border:0;border-radius:8px;padding:9px 16px;cursor:pointer}button.secondary{background:#e6f1fb;color:#185fa5}button.danger{background:#fcebeb;color:#a32d2d}p.tip{color:#5f6b78;font-size:13px}label{display:block;margin:12px 0 5px}li{padding:10px;border-bottom:1px solid #e6edf3;word-break:break-all}li a{margin-left:8px}small{color:#657685}#message{min-height:24px;color:#a32d2d}img{max-height:110px;max-width:180px;display:block}#app{display:none}</style><main><h1>校园网互传</h1><p class="tip">文字、截图和文件暂存到服务所在电脑。仅在可信网络中使用；HTTP 不加密。</p><section id="login"><label>用户名</label><input id="user" value="nay" autocomplete="username"><label>密码</label><input id="pass" type="password" autocomplete="current-password"><p><button onclick="login()">登录</button></p></section><section id="app"><p><button class="secondary" onclick="logout()">退出登录</button></p><h2>发送文字</h2><textarea id="note" placeholder="粘贴文字或链接"></textarea><p><button onclick="sendNote()">发送文字</button></p><h2>发送图片或文件</h2><p class="tip">支持 Ctrl+V 粘贴截图、一次选择多个文件或文件夹；单个文件最大 1 GB。</p><label>选择文件</label><input id="file" type="file" multiple><label>选择文件夹</label><input id="folder" type="file" webkitdirectory directory multiple><p><button onclick="sendFiles()">上传选中内容</button></p><h2>最近内容</h2><p><label><input id="selectAll" type="checkbox" onchange="toggleAll(this.checked)"> 全选</label><button class="secondary" onclick="refresh()">刷新</button><button class="secondary" onclick="downloadSelected()">下载选中</button><button class="secondary" onclick="downloadAll()">下载全部</button><button class="danger" onclick="deleteSelected()">删除选中</button></p><ul id="list"></ul></section><p id="message" role="status"></p></main><script>
let csrf=''; const $=id=>document.getElementById(id);
function msg(t){$('message').textContent=t}
async function request(path,opts={}){let headers={...(opts.headers||{})};if(csrf)headers['X-CSRF-Token']=csrf;let r=await fetch(path,{credentials:'same-origin',...opts,headers});let j=await r.json();if(!r.ok)throw Error(j.error||'请求失败');return j}
async function check(){try{let j=await request('/api/me');csrf=j.csrf;$('login').style.display='none';$('app').style.display='block';await refresh()}catch{ $('login').style.display='block';$('app').style.display='none'}}
async function login(){try{let j=await request('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({user:$('user').value,password:$('pass').value})});csrf=j.csrf;$('pass').value='';msg('登录成功');await check()}catch(e){msg(e.message)}}
async function logout(){try{await request('/api/logout',{method:'POST'})}catch{}csrf='';await check()}
async function sendNote(){let text=$('note').value.trim();if(!text)return msg('请先输入文字');try{await request('/api/note',{method:'POST',headers:{'Content-Type':'text/plain;charset=utf-8'},body:text});$('note').value='';msg('文字已发送');await refresh()}catch(e){msg(e.message)}}
async function sendFile(file,relative=''){if(!(file instanceof File))return sendFiles();if(file.size>1024*1024*1024)return msg('单个文件不能超过 1 GB');try{await request('/api/upload?name='+encodeURIComponent(relative||file.name),{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:file});msg(file.name+' 上传成功');await refresh()}catch(e){msg(file.name+'：'+e.message)}}
  async function sendFiles(){let selected=[...$('file').files].map(f=>({file:f,name:f.name}));let folders=[...$('folder').files].map(f=>({file:f,name:f.webkitRelativePath||f.name}));let files=[...selected,...folders];if(!files.length)return msg('请先选择文件或文件夹');if(files.length>500)return msg('一次最多上传 500 个文件');if(files.some(x=>x.file.size>1024*1024*1024))return msg('单个文件不能超过 1 GB');let batch=files.length>1||folders.length>0?'批次-'+new Date().toISOString().replace(/[:.]/g,'-'):'';let success=0;for(let i=0;i<files.length;i++){let path=(batch?batch+'/':'')+files[i].name;msg('正在上传 '+(i+1)+'/'+files.length+'：'+path);try{await request('/api/upload?name='+encodeURIComponent(path),{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:files[i].file});success++}catch(e){msg(path+'：'+e.message)}}$('file').value='';$('folder').value='';msg('已上传 '+success+'/'+files.length+' 个文件');await refresh()}
  function selectedIds(){return [...document.querySelectorAll('#list input.item-select:checked')].map(x=>x.value)}
  function toggleAll(checked){document.querySelectorAll('#list input.item-select').forEach(x=>x.checked=checked)}
  async function downloadSelected(){let ids=selectedIds();if(!ids.length)return msg('请先选择要下载的内容');window.location.href='/api/download-selected?ids='+encodeURIComponent(JSON.stringify(ids));msg('正在准备选中内容下载')}
  async function downloadAll(){window.location.href='/api/download-all';msg('正在准备全部内容下载')}
  async function deleteSelected(){let ids=selectedIds();if(!ids.length)return msg('请先选择要删除的内容');if(!confirm('确定删除选中的 '+ids.length+' 项？文件夹内的内容也会一起删除。'))return;try{let j=await request('/api/delete-selected',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ids})});msg('已删除 '+j.deleted+' 项');$('selectAll').checked=false;await refresh()}catch(e){msg(e.message)}}
  async function copyText(text){try{if(navigator.clipboard&&typeof navigator.clipboard.writeText==='function'){await navigator.clipboard.writeText(text);return true}}catch(e){}let ta=document.createElement('textarea');ta.value=text;ta.style.position='fixed';ta.style.opacity='0';document.body.appendChild(ta);ta.focus();ta.select();let ok=false;try{ok=document.execCommand('copy')}catch(e){}ta.remove();return ok}
  async function refresh(){try{let j=await request('/api/list');let ul=$('list');ul.replaceChildren();$('selectAll').checked=false;for(let item of j.items){let li=document.createElement('li');let select=document.createElement('input');select.type='checkbox';select.className='item-select';select.value=item.id;select.setAttribute('aria-label','选择 '+item.name);li.append(select,' ');let title=document.createElement('span');title.textContent=(item.type==='folder'?'📁 ':'')+item.name+(item.type==='folder'?' · '+item.count+' 个文件':' · '+(item.size/1024).toFixed(1)+' KB');li.append(title);if(item.type!=='folder'){let a=document.createElement('a');a.href='/api/download/'+encodeURIComponent(item.id);a.textContent='下载';li.append(a);if(item.name.endsWith('.txt')){let copy=document.createElement('button');copy.className='secondary';copy.textContent='复制文字';copy.onclick=async()=>{try{let r=await fetch(a.href,{credentials:'same-origin'});if(!r.ok)throw Error('读取失败');let ok=await copyText(await r.text());msg(ok?'已复制到剪贴板':'浏览器禁止剪贴板操作，请使用下载按钮后复制')}catch(e){msg(e.message)}};li.append(' ',copy)}}ul.append(li)}}catch(e){msg(e.message)}}
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

        def safe_relative(self, value):
            value = unquote(value).replace('\\', '/')
            parts = [p.strip().strip('.') for p in value.split('/') if p not in {'', '.', '..'}]
            if not parts or len('/'.join(parts)) > 240:
                return None
            cleaned = []
            for part in parts:
                part = ''.join(c for c in part if c.isprintable() and c not in '<>:"|?*')
                if part:
                    cleaned.append(part[:120])
            return Path(*cleaned) if cleaned else None

        def get_path(self, path):
            relative = self.safe_relative(path.rsplit('/', 1)[-1])
            if not relative:
                return None
            file = (root / relative).resolve()
            return file if file.is_file() and root in file.parents else None

        def get_tree_entry(self, value):
            relative = self.safe_relative(value)
            if not relative:
                return None
            target = (root / relative).resolve()
            return target if target == root or root in target.parents else None

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
                entries = []
                for child in sorted(root.iterdir(), key=lambda f: f.stat().st_mtime, reverse=True):
                    if child.is_file() and not child.is_symlink():
                        entries.append({'id': child.relative_to(root).as_posix(), 'name': child.name, 'type': 'file', 'size': child.stat().st_size})
                    elif child.is_dir() and not child.is_symlink():
                        count = sum(1 for f in child.rglob('*') if f.is_file() and not f.is_symlink())
                        size = sum(f.stat().st_size for f in child.rglob('*') if f.is_file() and not f.is_symlink())
                        entries.append({'id': child.relative_to(root).as_posix(), 'name': child.name, 'type': 'folder', 'count': count, 'size': size})
                return self.reply(200, {'items': entries[:200]})
            if path in {'/api/download-all', '/api/download-selected'}:
                selected = None
                if path == '/api/download-selected':
                    from urllib.parse import parse_qs
                    try:
                        selected = json.loads(parse_qs(urlsplit(self.path).query).get('ids', ['[]'])[0])
                    except (TypeError, ValueError):
                        return self.reply(400, {'error': '选择内容无效'})
                    if not isinstance(selected, list) or not selected or len(selected) > 500:
                        return self.reply(400, {'error': '请选择 1 到 500 项内容'})
                archive = tempfile.NamedTemporaryFile(prefix='校园网互传-', suffix='.zip', delete=False)
                archive.close()
                try:
                    with zipfile.ZipFile(archive.name, 'w', zipfile.ZIP_DEFLATED) as zf:
                        files = []
                        if selected is None:
                            files = [f for f in root.rglob('*') if f.is_file() and not f.is_symlink()]
                        else:
                            for item_id in selected:
                                target = self.get_tree_entry(str(item_id))
                                if not target or target == root:
                                    continue
                                if target.is_file():
                                    files.append(target)
                                elif target.is_dir():
                                    files.extend(f for f in target.rglob('*') if f.is_file() and not f.is_symlink())
                        for file in files:
                            zf.write(file, file.relative_to(root).as_posix())
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/zip')
                    archive_name = '校园网互传-全部内容.zip' if selected is None else '校园网互传-选中内容.zip'
                    self.send_header('Content-Disposition', "attachment; filename*=UTF-8''" + quote(archive_name))
                    self.send_header('Content-Length', str(Path(archive.name).stat().st_size))
                    self.send_header('X-Content-Type-Options', 'nosniff')
                    self.end_headers()
                    with open(archive.name, 'rb') as f:
                        while chunk := f.read(1024 * 1024):
                            self.wfile.write(chunk)
                finally:
                    Path(archive.name).unlink(missing_ok=True)
                return
            if path.startswith('/api/download/'):
                file = self.get_tree_entry(path[len('/api/download/'):])
                if not file or not file.is_file():
                    return self.reply(404, {'error': '文件不存在'})
                self.send_response(200)
                self.send_header('Content-Type', mimetypes.guess_type(file.name)[0] or 'application/octet-stream')
                self.send_header('Content-Disposition', "attachment; filename*=UTF-8''" + quote(file.name))
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
                relative = self.safe_relative(name)
                if not relative:
                    return self.reply(400, {'error': '文件名或相对路径无效'})
                target = (root / relative).resolve()
                if root not in target.parents:
                    return self.reply(400, {'error': '文件路径无效'})
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists():
                    return self.reply(409, {'error': '同名文件已存在，请先删除或更换文件夹'})
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
            if path == '/api/delete-selected':
                body = self.body(256 * 1024)
                if body is None:
                    return
                try:
                    selected = json.loads(body).get('ids', [])
                except (ValueError, AttributeError):
                    return self.reply(400, {'error': '选择内容无效'})
                if not isinstance(selected, list) or not selected or len(selected) > 500:
                    return self.reply(400, {'error': '请选择 1 到 500 项内容'})
                deleted = 0
                for item_id in selected:
                    target = self.get_tree_entry(str(item_id))
                    if not target or target == root or not target.exists():
                        continue
                    if target.is_dir():
                        shutil.rmtree(target)
                    elif target.is_file():
                        target.unlink()
                    deleted += 1
                return self.reply(200, {'ok': True, 'deleted': deleted})
            if path.startswith('/api/delete/'):
                target = self.get_tree_entry(path[len('/api/delete/'):])
                if not target or target == root:
                    return self.reply(404, {'error': '内容不存在'})
                if target.is_dir():
                    shutil.rmtree(target)
                elif target.is_file():
                    target.unlink()
                else:
                    return self.reply(404, {'error': '内容不存在'})
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