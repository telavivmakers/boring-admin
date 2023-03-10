#!/usr/bin/python
"""
Creates receipts in TAMI's accounting provider, from bank-reports.

input:   (XXXXX) bank's transactions list, in Excel format [currently: TSV from google-sheets]
output:  a new donation-recepit (type#405) at GreenInvoice.co.il

usage:
   bank2invoice.py  real <excel-file-1> [<excel-file-2> ...]   
   bank2invoice.py  search     # get latest existing receipts
   bank2invoice.py  test       # 

*REAL vs TEST modes:*
by default, running in TEST mode (inside a sandbox).
if you want to get things into the real accounting system, add the command line argument: real

The "test" command is using built-in data file, which is embedded in this module. 

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



""" # ----- copied from green_invoice/resources/resource.py,   merely for documentation! -----

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


# ----- end of documentation ---- """



# ------ CONSTs -------
flags = re.M+re.I+re.S
conffile = expanduser('~/.bank2invoice.ini')
#conf = Config(json_file=expanduser('~/.config/someapp.json'))
payment_type_map = {          # see docstring in guess_payment_type() 
    '^bit ?????????? ??????????$': 10,
    '.*??????????.*': 1,
}
INITIAL_LATEST_PAYMENT = '0000-00-00'
default_payment_type = 4    # bank wire
default_doctype = DocumentType.RECEIPT_FOR_DONATION
MAX_DAYS = 49    
BACK_DAYS = 40
banks = {
    4: "?????? ??????",
    6: "?????? ?????????? ??????????",
    9: "?????? ??????????",
    10: "?????? ??????????",
    11: "?????? ??????????????",
    12: "?????? ??????????????",
    13: "?????? ??????????",
    14: "?????? ???????? ??????????",
    17: "?????? ?????????????? ??????????????",
    20: "?????? ?????????? ??????????",
    22: "?????? CitiBank",
    23: "?????? HSBC",
    25: "?????? BNP Paribas",
    26: "?????? ??????????",
    27: "Barclays Bank PLC",
    31: "?????? ????????????????",
    34: "?????? ???????? ????????????",
    39: "?????? SBI State of India",
    43: "??'???????? ???????????? ?????? PLC.????????",
    46: "?????? ??????",
    48: "?????? ???????? ?????????? ????????????",
    50: '???????? ?????????? ?????????? (????"??)',
    52: "?????? ?????????? ?????????? ??????????",
    54: "?????? ??????????????",
    59: '????"??',
    65: "?????? ???????? ?????????? ????????????",
    66: "????????-??????????",
    67: "?????? Arab Land",
    68: "?????? ???????? ???????????? ????????????",
    68: "?????? ??????????",
    71: "???????????????? ??'????????",
    73: "?????? ??????????????",
    74: "???????????? ?????? ?????? ???????? ????????",
    76: "???????????? ????????????",
    77: "?????? ?????????? ??????????????????",
    82: "????-???????? ???????????? ??????????????",
    83: "???????????? ??????",
    84: "??????????????",
    89: "???????? ?????? ????????????",
    90: "?????? ?????????????? ??????????????????",
    93: "??'???????? ??????????",
    99: "?????? ??????????",
}

def err(msg, fatal=False):
    msg = msg.strip()
    if msg[:5].lower() != 'error':
        msg = 'ERROR: ' + msg
    sys.stderr.write(msg + '\n')
    if fatal:
        sys.exit()


def guess_payment_type(payment, conf):
    """ for guessing trx classification based on payment's comments. """
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
    """ convert dd/mm/yyyy (eu dates) to yyyy-mm-dd (ISO dates) """
    return re.sub(r'([0-3]\d)/([01]\d)/(20[23]\d)', r'\3-\2-\1', s, flags=flags)


def get_existing_documents(dtype):
    """ purpose:  to prevent duplicates,
    and to get last receipt date (cant add earlier reciept)"""

    # search documents since 100 days ago. earlier dates aren't relevant. I hope.
    from_date = (datetime.today() - timedelta(days=100)).strftime('%Y-%m-%d')
    to_date = iso_date()
    documentResource = DocumentResource()
    Payment.latest = INITIAL_LATEST_PAYMENT
    results = []
    docs = set()
    PAGES = 6    # just a random number; green-invoice's paging system is beyond logic. 6 sounds nice. 10 was taking too long. 1 page with pagesize 300 was giving only 25 recs per page anyway.

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
        # convert green-invoices entity to our Payment() object.  We need that to compare -> prevent  duplicates.
        doc = Payment( **dict(
            type=ret['type'],
            pay_date=ret['payment'][0]["date"],
            document_date=ret['documentDate'],
            amount=ret['amount'],
            client_name=ret['client']['name'],
            comments=ret['remarks']
        ) )
        docs.add(doc)   # unique items only
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
        env="sandbox",                     # actually i didn't test it yet in the real system.  donno whats this.
        api_key_id = conf.api_key_id,
        api_key_secret = conf.api_key_secret,
        logger=logging.root,
    )

    existing = get_existing_documents(default_doctype)  # for preventing duplicates, later

    s = open(xl_file).read()
    s = normalize_dates(s)  # convert israeli (european) dates to ISO dates:
                            # green-invoice requires them,
                            # plus we must sort by date.
    lines = s.splitlines()
    lines.sort()
    for line in lines:
        if not '\t' in line: continue    # empty lines
        if line[:2] !='20': continue     # must start with the year; otherwise it's a header line
        payment = Payment(line=line)
        if not payment:  continue
        if payment_exists(payment, existing):
            print('payment already in the system. skip')
            continue
        id, url = create_receipt(payment, conf)
        # @todo: send url to donnor. but we dont have their contact here.


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
            #"income": [    # ------- according to support, this is for ?????????????? ???? which we don't use in our non-profit org.
            #    {
            #        "price": payment.amount,
            #        "currency": payment.currency,
            #        "quantity": 1,
            #        "description": DEFAULT_TXN_DESCRIPTION,
            #        "vatType": IncomeVatType.DEFAULT,   # based on the business type
            #    }
            #],
            "payment": [    # ---- according to support, this is for ????????, which is the specific accounting status we use here.
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
    return id, url


class Payment:
    """ represents a transaction's data """
    
    latest = INITIAL_LATEST_PAYMENT     # global scope

    def __init__(self, **kw):
        """parse a line from the bank report;
        right now i've downloaded a tab-separated file from google-spreadsheet;
        
        overloaded usage:
            obj = Payment(line)   <- string, tab-separated, from excel
            obj = Payment({date:x, name:y, ...})   <- all object properties
        """
        self.type = default_doctype
        if 'line' in kw:
            parts = kw['line'].split('\t')
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
        """ represents the unique signature for transactions; 
        used for comparing against existing records/transactions: (pay1 == pay2) 
        we get from the bank these items:
          pay_date, client_name, bank, snif, account#, amount, comments  """
        
        return (self.type ==        other.type
            and self.pay_date ==    other.pay_date
            and self.amount ==      other.amount
            and self.client_name == other.client_name
            and self.comments ==    other.comments)     # this is tricky, @todo

    def __hash__(self):
        """ makes this class hashable; i'm using it to use within set() """
        return hash(f'{self.pay_date}{self.amount}{self.client_name}')


def iso_date():
    """ todays date as ISO """
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
?????????? ??????????	????	??????	????????	??????????	????????	??????????
29/12/2022	?????? ????????????	10	123	3434343	200.00	?????????????? ??????????
29/12/2022	?????? ???????? ????????	43	234	0	30.00	???????? ??????????
21/12/2022	Amd ????????	12	345	0	50.50	bit ?????????? ??????????
19/12/2022	???????? ????????	17	456	12345678	300.00
18/12/2022	?????? ????????????	20	567	987654	333.00	US PERSON ????????????
18/12/2026	?????? ????????????	20	567	987654	333.00	?????????? ?????? ??????
18/12/2021	?????? ??????????	34	567	987654	222.00	?????????? ?????? ??????
'''
    open(f,'w').write(test_data)
    main(f, conf)
    assert True   # @todo;  needs much better testing; 


conf = read_conf()
if f'{sys.version_info.major:02d}{sys.version_info.minor:02d}' < '0308':
    msg = f'WARNING !!! '*5 + f"\n 'bank2invoice.py' was tested on python 3.10, not on {sys.version_info.major}.{sys.version_info.minor}. OTOH yair wants to run it on py3.8, Let's see if it really does!"
    print(msg)
    err(msg)  # just a non blocking, non-fatal warning


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
    for arg in args:     # parsing command line without external tricks
        if 'search' in args:
            pass  # @todo; make it print existing transactions; No use for that now.

        elif 'test' in args:
            self_test()
            exit()

        elif arg[:6]=='--date':   # in case we want to register recepits as a certain date; not implemented(?)
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
