function openRazorpayCheckout(orderData) {
    var options = {
        "key": orderData.razorpay_key_id,
        "amount": orderData.amount * 100,
        "currency": orderData.currency,
        "name": "Booking Payment",
        "order_id": orderData.order_id,
        "handler": function (response){
            fetch('/payment/verify_payment', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    booking_id: orderData.booking_id,
                    order_id: response.razorpay_order_id,
                    payment_id: response.razorpay_payment_id,
                    signature: response.razorpay_signature
                })
            })
            .then(res => res.json())
            .then(data => {
                if(data.success){
                    window.location.href = '/payment/success';
                } else {
                    window.location.href = '/payment/failure';
                }
            });
        },
        "modal": {
            "ondismiss": function(){
                window.location.href = '/payment/failure';
            }
        }
    };
    var rzp = new Razorpay(options);
    rzp.open();
}
