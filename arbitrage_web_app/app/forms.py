from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, FieldList, FormField, TextAreaField
from wtforms.validators import DataRequired, Optional

class ExchangeConfigForm(FlaskForm):
    """Sub-form for a single exchange's configuration."""
    exchange_name = StringField('Exchange Name (must match CCXT ID, e.g., "binance", "kraken")', validators=[DataRequired()])
    apiKey = StringField('API Key', validators=[Optional()]) # Optional if exchange allows public access or key not needed
    secret = PasswordField('API Secret', validators=[Optional()])
    password = PasswordField('API Password (if required, e.g., for KuCoin)', validators=[Optional()])
    # Add other common CCXT parameters if needed, e.g., uid, login, etc.
    # Or a TextAreaField for 'other_params_json' to allow flexible JSON input for extra options.
    other_params_json = TextAreaField('Other Parameters (JSON format, e.g., {"options": {"adjustForTimeDifference": true}})', validators=[Optional()])


class AppConfigForm(FlaskForm):
    """Main form for application configurations."""
    cmc_api_key = StringField('CoinMarketCap API Key', validators=[Optional()])
    
    # Trading fees configuration - using TextAreaField for JSON input for simplicity
    # A more complex setup might use FieldList of FormFields for individual fee entries.
    trading_fees_json = TextAreaField('Trading Fees (JSON format, e.g., {"binance": 0.001, "default": 0.002})', 
                                      validators=[DataRequired()], 
                                      default='{\n  "default": 0.002,\n  "binance": 0.001,\n  "kraken": 0.0016\n}')

    # Exchange configurations - FieldList of ExchangeConfigForm
    exchanges = FieldList(FormField(ExchangeConfigForm), min_entries=1) # Require at least one exchange
    
    submit = SubmitField('Generate Configuration Output')
```
