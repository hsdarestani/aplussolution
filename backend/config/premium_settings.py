import os

SAML_ENABLED = os.getenv('SAML_ENABLED', '0') == '1'
SAML_SP_ENTITY_ID = os.getenv('SAML_SP_ENTITY_ID', '')
SAML_SP_ACS_URL = os.getenv('SAML_SP_ACS_URL', '')
SAML_SP_SLS_URL = os.getenv('SAML_SP_SLS_URL', '')
SAML_SP_X509_CERT = os.getenv('SAML_SP_X509_CERT', '').replace('\\n', '\n')
SAML_SP_PRIVATE_KEY = os.getenv('SAML_SP_PRIVATE_KEY', '').replace('\\n', '\n')
SAML_IDP_ENTITY_ID = os.getenv('SAML_IDP_ENTITY_ID', '')
SAML_IDP_SSO_URL = os.getenv('SAML_IDP_SSO_URL', '')
SAML_IDP_SLO_URL = os.getenv('SAML_IDP_SLO_URL', '')
SAML_IDP_X509_CERT = os.getenv('SAML_IDP_X509_CERT', '').replace('\\n', '\n')
SAML_EMAIL_ATTRIBUTE = os.getenv('SAML_EMAIL_ATTRIBUTE', 'email')
