# Razorpay Integration Deployment Notes

## Setting Environment Variables in Render
- Go to Render dashboard > Environment > Add Environment Variables
- Set:
    - RAZORPAY_KEY_ID
    - RAZORPAY_KEY_SECRET
    - RAZORPAY_WEBHOOK_SECRET
    - MONGODB_URI
- Never hardcode secrets in code or templates.

## Switching from Test Keys to Live Keys
- Replace test keys with live keys in Render environment variables.
- Update webhook secret accordingly.
- Test thoroughly in staging before switching to production.

## Regenerating Keys if Exposed
- Login to Razorpay dashboard > API Keys > Regenerate
- Update new keys in Render environment variables immediately.
- Rotate webhook secret as well.

## Settlement Flow Explanation
- Payments are captured by Razorpay and settled to your bank account as per Razorpay's settlement schedule.
- Use Razorpay dashboard to monitor settlements and payouts.

## Monitoring Failed Payments
- Use admin dashboard to track bookings with status 'failed' or 'pending'.
- Monitor payments collection for failed or unverified payments.
- Set up alerts/logging for webhook failures and payment errors.

## Security Checklist
- Always verify payment and webhook signatures server-side.
- Never confirm booking before verification.
- Use HTTPS for all endpoints.
- Rotate keys if exposed.
- Enable rate limiting and CSRF protection on payment endpoints.
- Log all payment events for audit.

## Production Recommendations
- Monitor logs and payment status regularly.
- Use structured logging and error handling.
- Test webhook and refund flows before going live.
- Keep Razorpay keys and secrets secure.
