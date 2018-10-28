MERCHANT_ID = 'mit_sao_mitoc'  # CyberSource merchant ID
PAYMENT_TYPE = 'membership'  # Value expected in mitoc-member processing code

# Labels and prices used when paying for memberships
# NOTE: If updating prices, you must also update:
# - `mitoc-member`: Ensures that the right price was paid for that affiliation
# - `amountFromAffiliation` (Angular directive): Sets the price actually paid in CyberSource
MIT_STUDENT = ('MIT Student', 15)
NON_MIT_STUDENT = ('Non-MIT Student', 20)
AFFILIATE = ('MIT affiliate', 30)
MIT_ALUM = ('MIT alum', 35)
GENERAL = ('Non-MIT affiliate', 40)
