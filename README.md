# bank2invoice

created by and for TAMI admins,
to automate boring accounting chores.


### Purpose
---
for each payment in bank report,
  creates a DONATION RECEIPT (type #405) entity in our account at "Heshbonit Yeruka" (AKA "morning")

### TODO
---
 1. read directly the bank's report.  currently the code is reading a Tab-Separated Value (tsv) which is downloaded from google, which is probably uploaded from the bank's excel, which is downloaded from the bank, had-gadya, had-gadya. Make the loop 1 step --- what's the first link we can attach to?

All other todo items are resolved yesterday 2023-02-16

	
### Install
---

adjust authentication and other params `bank2invoice.ini`

the project uses the [greeninvoice API](https://www.greeninvoice.co.il/api-docs), packed to a [pip](https://github.com/yanivps/green-invoice) by by yaniv (hi!),  
think of him when you 

`pip install green-invoice`



srsly now, tami automation team suggest to setup using python3.8[1]  

```bash
git clone git@github.com:telavivmakers/boring-admin.git 
cd boring-admin
python -m venv .venv
source ./.venv/scripts/activate #omit the source command on windows
./venv/scripts/pip install pip --update
pip install green_invoice requests
```

#### Windows Note:

The green_invoice module requires lxml v4.6.3, which is pain in the everything to install on Windows.  
So I downloaded the `green_invoice-1.2.1-py3-none-any.whl` package, and changed the requiremnts from `==4.6.3` to by `>= 4.6.3`,  hence my hacked `green_invoice.whl` is added to the repo.  and the latest binary lxml for my Windows x python version.



## OpSec
---

working Api Tokens in `.ini` need to be provided  
you should derive your own `.ini`, or get it from me, or from yair.    

ini file must be at your home dir (details inside the code)

tested on current bank report in google sheets (private link)

---
[notes]

[1] when did python 3.x versions became as fickel as an osx architecture change?!  - It's ok. Only the AttrDict might be tricky. And f'formatted{string}' was introduced only in 3.6.  So we're safe with 3.8
[2] [shahar]( shaharr.info) rocks the night sky! kicked working code, out the door, before your very eyes
