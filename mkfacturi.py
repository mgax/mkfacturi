#!/usr/bin/env python
# encoding: utf-8

import os.path
from datetime import timedelta
from decimal import Decimal
import flask
from flask.ext.script import Manager
from jinja2 import Markup, escape
import yaml

pages = flask.Blueprint('pages', __name__)

missing = object()


def q(value, places):
    return value.quantize(1 / Decimal(10 ** places))


defaults = {
    'name': None,
    'local': False,
    'details': "",
    'vat_number': "",
    'address': "",
    'delegate': "",
    'bank': "",
    'account': None,
    'accounts': {},
}


class Company(object):

    def __init__(self, data, code):
        self._data = data
        self.code = code

    def __getitem__(self, key):
        rv = self._data.get(key, missing)
        if rv is missing:
            rv = defaults.get(key)
        return rv


class Supplier(Company):

    def __init__(self, data, code):
        super(Supplier, self).__init__(data, code)
        self.invoice_number_format = data.get('invoice_number_format', '{}')

    def format_invoice_number(self, number):
        return self.invoice_number_format.format(number)


class Contract(object):

    def __init__(self, data, code, client):
        self._data = data
        self.code = code
        self.client = client

    def __getitem__(self, key):
        rv = self._data.get(key, missing)
        if rv is missing:
            rv = self.client[key]
        return rv


class Invoice(object):

    def __init__(self, data, supplier, contract):
        self._data = data

        self.supplier = supplier
        self.contract = contract
        self.code = "{s[date]}-{s[number]}".format(s=self)
        self.number = supplier.format_invoice_number(self['number'])
        self.due_date = self['date'] + timedelta(days=self['due_days'])
        self.quantity = Decimal(self['quantity'])
        self.exchange_rate = {k: Decimal(v) for k, v in
                              self['exchange_rate'].items()}

        price_per_unit = self['price_per_unit']
        price_per_unit_str, currency = price_per_unit.split()
        self.price_per_unit = Decimal(price_per_unit_str)
        self.currency = currency

        payment_currency = "RON" if self['local'] else self.currency
        self.payment_currency = payment_currency
        self.account = self['account'] or supplier['accounts'][payment_currency]

        if self['local']:
            exchange = self.exchange_rate[currency]
            self.price_per_unit = q(q(self.price_per_unit * exchange, 2), 4)
            self.total = q(self.price_per_unit * self.quantity, 2)
            self.total_ron = self.total

        else:
            self.total = q(self.price_per_unit * self.quantity, 2)
            self.total_ron = q(self.total * self.exchange_rate[currency], 2)

    def __getitem__(self, key):
        rv = self._data.get(key, missing)
        if rv is missing:
            rv = self.contract[key]
        return rv


    @property
    def client(self):
        return self.contract.client

    def __str__(self):
        return u"{s[date]} #{s[number]} – {s.client.code}".format(s=self)


class Model(object):

    def __init__(self, data):
        self.supplier = Supplier(data['supplier'], None)
        self.clients = {c: Company(d, c) for c, d in data['clients'].items()}
        self.contracts = {c: Contract(d, c, self.clients[d['client']])
                          for c, d in data['contracts'].items()}
        self.invoices = [
            Invoice(i, self.supplier, self.contracts[i['contract']])
            for i in data['invoices']
        ]


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
            if invoice['local']:
                flask.g.lang = 'ro'
            return flask.render_template('invoice_page.html', **{
                'supplier': model.supplier,
                'invoice': invoice,
                'client': invoice.client,
                'n': flask.request.args.get('n', '1', type=int),
            })

    else:
        flask.abort(404)


@pages.app_template_filter()
def nl2br(value):
    return escape(value).replace('\n', Markup('<br>\n'))


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
            print invoice['date'], invoice.total_ron

    return manager
