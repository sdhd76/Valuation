# Financial Valuation Web App

This is a FastAPI web application for financial statement extraction and valuation analysis, designed to run on Vercel.

## Features

- ✅ Extract financial statements from Yahoo Finance using yfinance API
- ✅ Perform Damodaran-style DCF valuation (FCFF/FCFE models)
- ✅ Interactive valuation assumptions
- ✅ Web-based interface with tabs and forms
- ✅ Responsive design

## Local Development

To run locally:
```bash
pip install -r requirements.txt
python Valuation.py
```

The app will run on http://localhost:8000

## Deployment to Vercel

1. **Install Vercel CLI:**
   ```bash
   npm install -g vercel
   ```

2. **Deploy:**
   ```bash
   cd /Users/Anthony/Valuation
   vercel
   ```

3. **Follow the prompts** to link your project and deploy

## Project Structure

- `Valuation.py` - Main FastAPI application with financial analysis functions
- `api/index.py` - Vercel serverless function entry point
- `templates/index.html` - Web interface template
- `static/` - Static files directory
- `requirements.txt` - Python dependencies
- `vercel.json` - Vercel deployment configuration

## API Endpoints

- `GET /` - Main page
- `POST /extract` - Extract financial data and run valuation
- `POST /recalculate` - Recalculate valuation with custom assumptions

The app is now fully compatible with Vercel's serverless environment and ready for deployment!
