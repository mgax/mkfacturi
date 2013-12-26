#!/usr/bin/env python
# encoding: utf-8

import os.path
from datetime import timedelta
from decimal import Decimal
import flask
from flask.ext.script import Manager
import yaml

pages = flask.Blueprint('pages', __name__)


def q(value, places):
    return value.quantize(1 / Decimal(10 ** places))


class Company:

    def __init__(self, data, code):
        self.code = code
        self.name = data['name']
        self.local = data.get('local')
        self.details = data['details']
        self.address = data['address']
        self.delegate = data['delegate']
        self.bank = data['bank']
        self.accounts = data.get('accounts')


class Contract:

    def __init__(self, data, code, client):
        self.code = code
        self.client = client
        self.due_days = data['due_days']
        self.unit = data['unit']
        self.price_per_unit = data['price_per_unit']


class Invoice:

    def __init__(self, data, contract):
        self.contract = contract
        self.code = "{data[date]}-{data[number]}".format(data=data)
        self.number = data['number']
        self.date = data['date']
        self.due_date = self.date + timedelta(days=self.contract.due_days)
        self.product = data['product']
        self.quantity = data['quantity']
        self.exchange_rate = {k: Decimal(v) for k, v in
                              data['exchange_rate'].items()}
        price_per_unit_str, currency = self.contract.price_per_unit.split()
        self.price_per_unit = Decimal(price_per_unit_str)

        if self.local:
            exchange = self.exchange_rate[currency]
            self.price_per_unit = q(q(self.price_per_unit * exchange, 2), 4)
            self.total = q(self.price_per_unit * self.quantity, 2)
            self.total_ron = self.total

        else:
            self.total = q(self.price_per_unit * self.quantity, 2)
            self.total_ron = q(self.total * self.exchange_rate[currency], 2)

    @property
    def client(self):
        return self.contract.client

    @property
    def local(self):
        return self.client.local

    def __str__(self):
        return u"{s.date} #{s.number} – {s.client.code}".format(s=self)


class Model:

    def __init__(self, data):
        self.supplier = Company(data['supplier'], None)
        self.clients = {c: Company(d, c) for c, d in data['clients'].items()}
        self.contracts = {c: Contract(d, c, self.clients[d['client']])
                          for c, d in data['contracts'].items()}
        self.invoices = [Invoice(i, self.contracts[i['contract']])
                         for i in data['invoices']]


def read_model():
    with open(flask.current_app.config['DATAFILE'], 'rb') as f:
        return Model(yaml.load(f))


@pages.route('/')
def home():
    return flask.render_template('home.html', model=read_model())


@pages.route('/invoice/<code>')
def invoice(code):
    model = read_model()
    for invoice in model.invoices:
        if invoice.code == code:
            if invoice.local:
                flask.g.lang = 'ro'
            return flask.render_template('invoice_page.html', **{
                'supplier': model.supplier,
                'invoice': invoice,
                'client': invoice.client,
                'currency': "RON" if invoice.local else "EUR",
                'n': flask.request.args.get('n', '1', type=int),
            })

    else:
        flask.abort(404)


@pages.app_template_filter('datefmt')
def datefmt(date):
    return date.strftime('%d.%m.%Y')


@pages.app_url_defaults
def bust_cache(endpoint, values):
    if endpoint == 'static':
        filename = values['filename']
        file_path = os.path.join(flask.current_app.static_folder, filename)
        if os.path.exists(file_path):
            mtime = os.stat(file_path).st_mtime
            key = ('%x' % mtime)[-6:]
            values['t'] = key


def translate(text_en, text_ro):
    return text_ro if flask.g.get('lang') == 'ro' else text_en


def create_app():
    app = flask.Flask(__name__)
    app.config.from_pyfile(os.path.join(app.root_path, 'settings.py'))
    app.register_blueprint(pages)
    app.jinja_env.globals['_'] = translate
    return app


def create_manager(app):
    manager = Manager(app)

    @manager.command
    def dump():
        model = read_model()
        for invoice in model.invoices:
            print invoice.date, invoice.total_ron

    return manager
