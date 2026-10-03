"""Portable startup entry point used by all platform launchers."""
import sys
if sys.version_info < (3, 11):
    raise SystemExit('需要 Python 3.11 或以上版本，请从 python.org 安装后重新启动。')
import os
import errno
import webbrowser
import server

def main():
    try:
        requested_port = int(os.getenv('PORT', '8765'))
        if not 1 <= requested_port <= 65535:
            raise ValueError
    except ValueError:
        print('PORT 必须是 1–65535 的整数，请检查 .env。')
        return 1
    host = os.getenv('HOST', '0.0.0.0')
    http = None
    for port in range(requested_port, min(requested_port + 20, 65536)):
        try:
            http = server.ThreadingHTTPServer((host, port), server.Handler)
            break
        except OSError as exc:
            if exc.errno != errno.EADDRINUSE:
                print(f'启动失败：{exc}')
                return 1
    if http is None:
        print('连续 20 个端口都被占用，请关闭旧服务或修改 .env 中的 PORT。')
        return 1
    if port != requested_port:
        print(f'端口 {requested_port} 已被占用，当前这份程序改用 {port}。', flush=True)
    try:
        server.init_db()
    except Exception:
        http.server_close()
        raise
    print(f'当前程序目录：{server.ROOT}', flush=True)
    print('OCR：' + ('已配置' if server.ocr_cloud.configuration()['configured'] else '未配置，请在 .env 中填写 OCR_API_KEY'), flush=True)
    print(f'一扫开店已启动：http://localhost:{port}', flush=True)
    print('保持此窗口打开；按 Ctrl+C 停止服务。', flush=True)
    print('新用户请注册小店，已有账号请登录。', flush=True)
    if '--no-browser' not in sys.argv:
        if not webbrowser.open(f'http://localhost:{port}'):
            print(f'浏览器未自动打开，请手动访问 http://localhost:{port}。', flush=True)
    try:
        http.serve_forever()
    except KeyboardInterrupt:
        print('\n服务已停止。')
    finally:
        http.server_close()
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
