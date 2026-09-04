export interface BuyerChatRequest {
  merchant_id: string;
  message: string;
}

export interface BuyerChatProduct {
  product_id: string;
  name: string;
  price: string;
  currency: string;
  similarity: number;
}

export interface BuyerChatResponse {
  merchant_id: string;
  message: string;
  products: BuyerChatProduct[];
}

export interface ChatMessage {
  id: string;
  role: "buyer" | "assistant";
  text: string;
  products?: BuyerChatProduct[];
}

// Checkout types
export interface CheckoutRequest {
  merchant_id: string;
  product_id: string;
  quantity: number;
}

export interface CheckoutResponse {
  order_id: string;
  razorpay_order_id: string;
  razorpay_key_id: string;
  amount_paise: number;
  currency: string;
  product_name: string;
  unit_price: string;
  total_amount: string;
  quantity: number;
  merchant_name: string;
  status: string;
  environment: string;
}

export interface PaymentVerifyRequest {
  order_id: string;
  razorpay_order_id: string;
  razorpay_payment_id: string;
  razorpay_signature: string;
}

export interface PaymentVerifyResponse {
  order_id: string;
  status: string;
  razorpay_payment_id: string | null;
  total_amount: string | null;
  idempotent: boolean;
}
