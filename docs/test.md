# test.md

初始化沙箱：

https://code.coze.cn/api/ideserver_api/sandbox/init_sandbox?msToken=kaGejykT7-hxZ_iwggAVcUfzKRFmbuq2hBERuQhHuqDWE83CBnfJwjJNQVjgukmNoFPDL59A15XgDhFrL1LC_7VbMczYzBauCWlfLvNJr3zDXSnZCsLZNXUnzzrY5ryz&a_bogus=E7WhQRLvdDDpfVgk5l%2FLfY3qVRxQYZme0SVkMDheQ1F7Ag39HMOi9exobkUvud8jF4%2FJIe8jy4hbYroBrQQJ01wfHS0O%2F2Cgs600tMBk-nSb5NiruyUgrzXw-hsAteeQsv-5iQfkqw%2FeFuRDA2xamhqvPjoja3LkTiyxypaC3pHB


返回：{
    "code": 0,
    "msg": "",
    "project_host": "4411586d-d24a-4aec-97c1-0cf0189b7430.dev.coze.site",
    "token": "",
    "ws_url": "wss://code.coze.cn/ws/devbox/7666028792145805318/api/ws?source=ide"
}


接口：wss://code.coze.cn/ws/devbox/7700808859971141641/api/ws?source=ide&user_id=2556797773415833&ts=1793066083066


发送：{"jsonrpc":"2.0","id":3,"method":"file.stat","params":{"path":""}}

{"jsonrpc": "2.0", "method": "web.server_status_changed", "params": {"status": "ready", "preview_enable": "", "preview": {"worktree_name": "", "branch": "main", "status": "running", "preview_enabled": true, "preview_url": "https://8fbbe450-0c99-44c3-ac15-1daca69c9b8a-5000.dev.coze.site", "running_previews": 1, "max_previews": 5}}}

发送：
{"jsonrpc":"2.0","id":6,"method":"web.preview_status","params":{}}

接收：
{"jsonrpc":"2.0","id":6,"result":{"worktree_name":"","branch":"main","status":"running","preview_enabled":true,"preview_url":"https://8fbbe450-0c99-44c3-ac15-1daca69c9b8a-5000.dev.coze.site","running_previews":1,"max_previews":5,"sub_id":null,"project_type":null}}

## 关于文件ws
发送：
{"jsonrpc":"2.0","id":73,"method":"file.read","params":{"path":".gitignore"}}
接受：
{"jsonrpc":"2.0","id":73,"result":{"content":"xxxx","encoding":"utf-8","size":1664,"mtime":1783492844348,"ctime":1794882020957,"totalLine":165}}

发送：
{"jsonrpc":"2.0","id":15,"method":"file.stat","params":{"path":"src"}}
接受：
{"jsonrpc":"2.0","id":15,"result":{"path":"src","size":4096,"mtime":1784889347088,"ctime":1794882021102,"isDirectory":true,"isFile":false,"isSymbolicLink":false,"permissions":"755","children":[{"name":"data","isDirectory":true,"size":4096,"mtime":1784889387577},{"name":"lib","isDirectory":true,"size":4096,"mtime":1784889625547},{"name":"components","isDirectory":true,"size":4096,"mtime":1794819237556},{"name":"store","isDirectory":true,"size":4096,"mtime":1784169391327},{"name":"hooks","isDirectory":true,"size":4096,"mtime":1783492844345},{"name":"server.ts","isDirectory":false,"size":978,"mtime":1783492844344},{"name":"app","isDirectory":true,"size":4096,"mtime":1784889635900}]}}