#!/usr/bin/python
"""
TAMI invoice bank-to-invoice connection
receive:   (XXXXX) bank's transactions list, in Excel format
purpose:
    issue invoices
    (maybe) send them to whoever.

usage:
   bank2invoice.py  real <excel-file-1> [<excel-file-2> ...]
   bank2invoice.py  search
   bank2invoice.py  test

by default, running in TEST mode (inside a sandbox)
if you want to get things into the real accounting system,
add the command line argument: real

test is using built-in data file, which is embedded in this file

started by shaharr.info,
on request of yair, 2023-02-15

"""


import os, re, sys, time
from os.path import expanduser, expandvars, isdir, isfile, join, basename, abspath, splitext, getsize, dirname
from os import mkdir, chdir, rename, unlink, walk, popen
from json import dumps, loads
from glob import iglob
from time import sleep, time as currtime
from datetime import timedelta, datetime
import logging
import requests
import tempfile

import green_invoice
from green_invoice.models import (
    Currency,
    DocumentLanguage,
    DocumentType,
    PaymentCardType,
    PaymentDealType,
    PaymentType,
    IncomeVatType,
)
from green_invoice.resources import DocumentResource


class AttrDict(dict):
    """ acces dictionary data (dic['key']) as objects (dic.key) """
    def __init__(self, *args, **kwargs):
        super(AttrDict, self).__init__(*args, **kwargs)
        self.__dict__ = self



"""
class DocumentType(enum.IntEnum):
    PRICE_QUOTE = 10
    ORDER = 100
    DELIVERY_NOTE = 200
    RETURN_DELIVERY_NOTE = 210
    TRANSACTION_ACCOUNT = 300
    TAX_INVOICE = 305
    TAX_INVOICE_RECEIPT = 320
    REFUND = 330
    RECEIPT = 400
    RECEIPT_FOR_DONATION = 405
    PURCHASE_ORDER = 500
    RECEIPT_OF_A_DEPOSIT = 600
    WITHDRAWAL_OF_DEPOSIT = 610


class DocumentStatus(enum.IntEnum):
    OPENED_DOCUMENT = 0
    CLOSED_DOCUMENT = 1
    MANUALLY_MARKED_AS_CLOSED = 2
    CANCELING_OTHER_DOCUMENT = 3
    CANCELED_DOCUMENT = 4


class DocumentLanguage(str, enum.Enum):
    HEBREW = "he"
    ENGLISH = "en"


class Currency(str, enum.Enum):
    ILS = "ILS"
    USD = "USD"
    EUR = "EUR"
    GBP = "GBP"


class PaymentType(enum.IntEnum):
    UNPAID = -1
    DEDUCTION_AT_SOURCE = 0
    CASH = 1
    CHECK = 2
    CREDIT_CARD = 3
    ELECTRONIC_FUND_TRANSFER = 4
    PAYPAL = 5
    PAYMENT_APP = 10
    OTHER = 11


"""



# ------ CONSTs -------
flags = re.M+re.I+re.S
conffile = expanduser('~/.bank2invoice.ini')
#conf = Config(json_file=expanduser('~/.config/someapp.json'))
payment_type_map = {
    '^bit העברת כספים$': 10,
    '.*מזומן.*': 1,
}
INITIAL_LATEST_PAYMENT = '0000-00-00'
default_payment_type = 4    # bank wire
default_doctype = DocumentType.RECEIPT_FOR_DONATION
MAX_DAYS = 49
BACK_DAYS = 40
banks = {
    4: "בנק יהב",
    6: "בנק מזרחי טפחות",
    9: "בנק הדואר",
    10: "בנק לאומי",
    11: "בנק דיסקונט",
    12: "בנק הפועלים",
    13: "בנק איגוד",
    14: "בנק אוצר החייל",
    17: "בנק מרכנתיל דיסקונט",
    20: "בנק מזרחי טפחות",
    22: "בנק CitiBank",
    23: "בנק HSBC",
    25: "בנק BNP Paribas",
    26: "בנק יובנק",
    27: "Barclays Bank PLC",
    31: "בנק בינלאומי",
    34: "בנק ערבי ישראלי",
    39: "בנק SBI State of India",
    43: "ג'ורדן נשיונל בנק PLC.עמאן",
    46: "בנק מסד",
    48: "בנק קופת העובד הלאומי",
    50: 'מרכז סליקה בנקאי (מס"ב)',
    52: "בנק פועלי אגודת ישראל",
    54: "בנק ירושלים",
    59: 'שב"א',
    65: "חסך קופת חסכון לחינוך",
    66: "קהיר-עומאן",
    67: "בנק Arab Land",
    68: "בנק אוצר השלטון המקומי",
    68: "בנק דקסיה",
    71: "קומרשיאל ג'ורדן",
    73: "ערב איסמליק",
    74: "בריטיש בנק אוף מידל איסט",
    76: "השקעות פלשתין",
    77: "בנק לאומי למשכנתאות",
    82: "אל-קודס לפיתוח והשקעות",
    83: "יוניון בנק",
    84: "האוזינג",
    89: "מספר בנק פלסטין",
    90: "בנק דיסקונט למשכנתאות",
    93: "ג'ורדן כווית",
    99: "בנק ישראל",
}

def err(msg, fatal=False):
    msg = msg.strip()
    if msg[:5].lower() != 'error':
        msg = 'ERROR: ' + msg
    sys.stderr.write(msg + '\n')
    if fatal:
        sys.exit()


def guess_payment_type(payment, conf):
    for key in payment_type_map.keys():
        if re.match(key, payment.comments):
            return payment_type_map[key]
    return default_payment_type


def read_conf():
    conf = AttrDict()
    if not isfile(conffile):
        err(f'config file (with top secret data!!) is not found in {conffile} !', True)
    for line in open(conffile).read().splitlines():
        if '=' in line and line[0]!='#':
            k, v = line.split('=',2)
            conf[k.strip()] = v.strip()
    return conf

def normalize_dates(s):
    return re.sub(r'([0-3]\d)/([01]\d)/(20[23]\d)', r'\3-\2-\1', s, flags=flags)


def get_existing_documents(dtype):
    """ purpose:  to prevent duplicates,
    and to get last receipt date (cant add earlier reciept)"""

    # search documents since 100 days ago
    from_date = (datetime.today() - timedelta(days=100)).strftime('%Y-%m-%d')
    to_date = iso_date()
    documentResource = DocumentResource()
    Payment.latest = INITIAL_LATEST_PAYMENT
    results = []
    docs = set()
    PAGES = 6

    for page in range(PAGES):
        print(f'downloading existing docs, page {page} / {PAGES}')

        params = dumps({
            "page": page, "pageSize": 50,
            "type": [ dtype ], "sort": "documentDate",
            "fromDate": from_date, "toDate": to_date,
          })
        page_results = documentResource.search_document(params)
        page_results = page_results['items']
        if not page_results: break
        print(f'{len(page_results)=}')
        results.extend(page_results)


    for ret in results:
        #print(ret)
        doc = Payment( **dict(
            type=ret['type'],
            pay_date=ret['payment'][0]["date"],
            document_date=ret['documentDate'],
            amount=ret['amount'],
            client_name=ret['client']['name'],
            comments=ret['remarks']
        ) )
        docs.add(doc)
        Payment.latest = max(Payment.latest, doc.pay_date)
        print(f'{Payment.latest=} vs. {doc.pay_date=}')
    return docs


def payment_exists(payment, existing):
    for doc in existing:
        print(f'{payment.comments=}  >>>  {doc.comments=}')
        if doc==payment:
            return True

    return False


def main(xl_file, conf):
    green_invoice.client.configure(
        env="sandbox",
        api_key_id = conf.api_key_id,
        api_key_secret = conf.api_key_secret,
        logger=logging.root,
    )

    existing = get_existing_documents(default_doctype)  # needed to prevent duplicates

    s = open(xl_file).read()
    s = normalize_dates(s)  # convert israeli (european) dates to ISO dates
                            # green-invoice requires them,
                            # plus we must sort by date.
    lines = s.splitlines()
    lines.sort()
    for line in lines:
        if not '\t' in line: continue      # empty lines
        if line[:2] !='20': continue   # should be year; header lines
        payment = Payment(line=line)
        if not payment:  continue
        if payment_exists(payment, existing):
            print('payment already documented')
            continue
        id, url = create_receipt(payment, conf)
        #.


def create_receipt(payment, conf):
    documentResource = DocumentResource()
    payment_type = PaymentType.ELECTRONIC_FUND_TRANSFER

    today = datetime.today()
    doc_date = max( Payment.latest, payment.pay_date)      # latest from payment vs. latest receipt
    days = (today - datetime.fromisoformat(doc_date)).days # how many days ago is it?
    if days >= MAX_DAYS:                                   # if too many days,
        doc_date = (today - timedelta(days=BACK_DAYS)).strftime('%Y-%m-%d')  # set to 40 days ago

    print(f'{doc_date=} | {payment.pay_date=} | {Payment.latest=} | {iso_date()=}')
    doc = documentResource.create(
        {
            "type": default_doctype,   # see types above
            "client": { "name": payment.client_name, "add": False, },
            "currency": payment.currency,
            "lang": DocumentLanguage.HEBREW,
            "date": doc_date,
            "signed": True,
            "rounding": False,
            "remarks": payment.comments,
            #"income": [
            #    {
            #        "price": payment.amount,
            #        "currency": payment.currency,
            #        "quantity": 1,
            #        "description": DEFAULT_TXN_DESCRIPTION,
            #        "vatType": IncomeVatType.DEFAULT,   # based on the business type
            #
            #    }
            #],
            "payment": [
                {
                    "type": guess_payment_type(payment, conf),
                    "date": payment.pay_date,
                    "dealType": PaymentDealType.REGULAR,
                    #"cardNum": "4242",
                    #"cardType": PaymentCardType.VISA,
                    "bankName": banks.get(payment.bank, 0),
                    "bankBranch": str(payment.snif),
                    "bankAccount": str(payment.account),
                    "price": payment.amount,
                    "currency": payment.currency,
                }
            ],
        }
    )
    id = doc['id']
    url = doc['id']
    #get_document_download_link(id)
    return id, url




class Payment:
    latest = INITIAL_LATEST_PAYMENT

    def __init__(self, **kw):
        """parse a line from the bank report;
        right now i've downloaded a tab-separated file from google-spreadsheet;
        overloaded usage:
            obj = Payment(line)   <- string, tab-separated, from excel
            obj = Payment({date:x, name:y, ...})   <- all object properties
        """
        kw = AttrDict(kw)
        self.type = default_doctype
        if 'line' in kw:
            parts = kw.line.split('\t')
            if len(parts) != 7:
                print('shit, bank data record must have 7 columns exactly')
                raise Exception   # either a bug, or format change, must re-adapt the code !
            self.pay_date, self.client_name, self.bank, self.snif, self.account, amount, self.comments = parts
            #self.pay_date = f'{d[6:10]}-{d[3:5]}-{d[0:2]}'   # european date to ISO
            self.amount = float(amount)
            self.currency = Currency.ILS     # default?!??! assumption...

        else:
            for k,v in kw.items():
                setattr(self, k, v)


    def __eq__(self, other):
        #self.pay_date, self.client_name, self.bank, self.snif, self.account, self.amount, self.comments
        return (self.type ==        other.type
            and self.pay_date ==    other.pay_date
            and self.amount ==      other.amount
            and self.client_name == other.client_name
            and self.comments ==    other.comments)     # this is tricky, @todo

    def __hash__(self):
        return hash(f'{self.pay_date}{self.amount}{self.client_name}')


def iso_date():
    return datetime.today().strftime('%Y-%m-%d')

def self_test():
    conf = read_conf()
    conf.test = True
    conf.api_key_id = conf.sanbox_api_id
    conf.api_key_secret = conf.sandbox_api_secret
    conf.api_url = conf.sandbox_api_url
    f = tempfile.mktemp(prefix='tami-kabala-test', suffix='.test')
    test_data = '''
# this is a comment
תאריך רישום	שם	בנק	סניף	חשבון	סכום	הערות
29/12/2022	גגג גוגייג	10	123	3434343	200.00	במעטפות שמנות
29/12/2022	צגי גגוג גוגג	43	234	0	30.00	סדנת עיזים
21/12/2022	Amd גייג	12	345	0	50.50	bit העברת כספים
19/12/2022	גגיג גוגי	17	456	12345678	300.00
18/12/2022	גגג גגיגיג	20	567	987654	333.00	US PERSON תרומות
18/12/2026	גגג גגיגיג	20	567	987654	333.00	תאריך חדש מדי
18/12/2021	גגג גגגיג	34	567	987654	222.00	תאריך ישן מדי
'''
    open(f,'w').write(test_data)
    main(f, conf)


conf = read_conf()
if f'{sys.version_info.major:02d}{sys.version_info.minor:02d}' < '0310':
    msg = f'WARNING !!! '*5 + f'\n "bank2invoice.py" was tested on python 3.10, not on {sys.version_info.major}.{sys.version_info.minor}.'
    print(msg)
    err(msg)



if __name__ == "__main__":
    args = sys.argv[1:]
    conf.test = 'real' not in args
    conf.writing_date = None   # meaning,

    if conf.test:
        conf.api_key_id = conf.sanbox_api_id
        conf.api_key_secret = conf.sandbox_api_secret
        conf.api_url = conf.sandbox_api_url
        print('test mode')

    files = set()
    for arg in args:
        if 'search' in args:
            pass

        elif 'test' in args:
            self_test()
            exit()

        elif arg[:6]=='--date':
            d = arg[7:]
            today = iso_date()
            if not re.match(r'^20[23]\d-[01]\d-[0-3]\d$', d) or arg <= today:
                err('bad writing date, or writing date in the future', True)
            else:
                conf.writing_date = arg

        elif isfile(arg):
            files.add(arg)


    for f in files:
        main(f, conf)

    if not files:   # if no data to process
        print(__doc__)
        err('warning: no bank files provided', True)

    print(f'{c} records added')
