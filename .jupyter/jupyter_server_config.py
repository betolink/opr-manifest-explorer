# Jupyter server configuration for Panel proxy
c.ServerProxy.servers = {
    'panel': {
        'command': ['panel', 'serve', 'explorer.py', '--address', '0.0.0.0', '--port', '{port}', '--allow-websocket-origin=*'],
        'timeout': 300,
        'launcher_entry': {
            'enabled': True,
            'title': 'Panel App',
        },
    },
}