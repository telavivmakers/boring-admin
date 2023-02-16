bank2invoice
===============
created by and for TAMI admins,
to automate boring accounting chores.


purpose:

for each payment in bank report,
  creates a DONATION RECEIPT (type #405) entity in our account at "Heshbonit Yeruka" (AKA "morning")

todo:
=============
		למיין לפי תאריך ולהזין  אותם בסדר עולה מהישן לחדש 
		לבדוק קודם את תאריך הקבלה האחרונה שיצאה, כדי להתחיל לא מוקדם מהתאריך הזה.
		לבדוק שאין כפילויות.  כרגע המערכת שלהם מאפשרת לי ליצור 2 קבלות עם אותם נתונים, בלי שום הערה או אזהרה

install:
==========
adjust authentication and other params bank2invoice.ini

Windows Note:
--------------
The green_invoice module requires lxml v4.6.3, which is pain in the everything to install on Windows.
So I downloaded the green_invoice-1.2.1-py3-none-any.whl package, and changed the requiremnts from ==4.6.3 to by >= 4.6.3,  hence my hacked "green_invoice.whl" is added to the repo, and the latest binary lxml for my Windows x python version.
`pip install green_invoice`

In linux it should install easily with just `pip install green_invoice`

"""

ini file is NOT added to the github repo, for seurity reasons.
you should derive your own ini, or get it from me, or from yair.
ini file must be at your home dir (details inside the code)


tested on current bank report in google sheets (private link)
