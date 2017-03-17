# -*- coding: utf-8 -*-
import json
import os

from flask import Flask

app = Flask(__name__)

app_name = os.environ.get('APP_NAME', 'World')
container_id = os.environ.get('CONTAINER_ID')


@app.route('/')
def hello_world():
    ret = '<pre>Hello %s' % app_name
    if container_id:
        ret += '\nRunning inside container %s' % container_id
    os_environment_json = json.dumps(
        dict(os.environ),
        sort_keys=True,
        indent=4,
        separators=(',', ':'),
    )
    ret += '\nEnvironment dump:\n%s' % os_environment_json
    ret += '\n</pre>\n'
    return ret


if __name__ == '__main__':
    app.run(
        debug=True,
        port=8069,
        host='0.0.0.0',
    )
