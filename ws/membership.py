MERCHANT_ID = 'mit_sao_mitoc'  # CyberSource merchant ID
PAYMENT_TYPE = 'membership'  # Value expected in mitoc-member processing code

# Labels and prices used when paying for memberships
# If we change these membership prices/tiers, we'll need to also change
# the processing logic in mitoc-member.
STUDENT = ('Student', 15)
AFFILIATE = ('MIT affiliate', 20)
GENERAL = ('Non-MIT affiliate', 25)

MEMBERSHIP_LEVELS = [STUDENT, AFFILIATE, GENERAL]
