Fix 1 - Sports (Basketball/Tennis + League) server patch
Replace these 3 files in your project (same names):
  extended_schema.py, webapp_api.py, app.js
Also DELETE from project: webapp_api_errors.log
Test: python sports_league_regression_test.py  -> SPORTS_LEAGUE_REGRESSION=PASS
