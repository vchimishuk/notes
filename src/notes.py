import re
from io import StringIO
from datetime import datetime
from dateutil import tz
from pymongo import MongoClient
from flask import Flask
from flask import request, redirect
from flask import render_template, make_response
from configparser import ConfigParser


CONF_FILE = '/etc/notes.conf'
TEMPLATE_DIR = '/usr/share/notes/templates'


def read_config(path):
    p = ConfigParser()

    with open(path) as f:
        s = StringIO('[main]\n' + f.read())
        p.readfp(s)

    return p['main']


config = read_config(CONF_FILE)
client = MongoClient(config['db.host'], int(config['db.port']))
db = client[config['db.name']]
notes = db.notes
counters = db.counters
app = Flask('Notes', template_folder=TEMPLATE_DIR)


counters.update_one({'_id': 'postId'}, {'$setOnInsert': {'value': 1}}, upsert=True)


def next_id():
    doc = counters.find_one_and_update({'_id': 'postId'}, {'$inc': {'value': 1}})

    return doc['value']


def note_preview(note):
    time = note['time'].replace(tzinfo=tz.tzutc())
    local_time = time.astimezone(tz.tzlocal())

    content = re.sub(r'\s+', ' ', note['content'].strip())
    if len(content) > 80:
        content = content[:80] + '...'

    return {'id': note['_id'],
            'time': local_time.strftime('%d.%m.%Y %H:%M'),
            'content': content}


@app.route('/favicon.ico')
def favicon():
    return 'Not found', 404


@app.route('/', methods=['GET', 'POST'])
def create():
    if request.method == 'POST':
        content = request.form['content']
        if not len(content.strip()):
            return redirect('/')

        note = {'_id': next_id(),
                'time': datetime.utcnow(),
                'content': content}
        id = notes.insert_one(note).inserted_id

        return redirect('/' + str(id))
    else:
        docs = map(lambda n: note_preview(n),
                   notes.find(sort=[('_id', -1)], limit=5))

        return render_template('create.html', notes=docs)


@app.route('/edit/<int:id>', methods=['GET', 'POST'])
def edit(id):
    doc = notes.find_one({'_id': id})
    if doc is None:
        return 'Not found', 404

    if request.method == 'POST':
        content = request.form['content']

        if len(content.strip()):
            doc['content'] = content
            doc['time'] = datetime.utcnow()

            notes.update_one({'_id': doc['_id']}, {'$set': doc})

        return redirect('/' + str(id))
    else:
        docs = map(lambda n: note_preview(n),
                   notes.find(sort=[('_id', -1)], limit=5))

        return render_template('create.html', note=doc, notes=docs)


@app.route('/<int:id>', methods=['DELETE'])
def delete(id):
    notes.delete_one({'_id': id})

    return ''


@app.route('/<int:id>', methods=['GET'])
def view(id):
    headers = {'Content-Type': 'text/plain'}
    note = notes.find_one({'_id': id})

    if note is None:
        return 'Not found', 404

    return make_response((note['content'], 200, headers))


@app.route('/history', methods=['GET'])
def history():
    docs = map(lambda n: note_preview(n),
               notes.find(sort=[('_id', -1)], limit=100))

    return render_template('history.html', notes=docs)


if __name__ == '__main__':
    app.run(config['http.address'], int(config['http.port']))
