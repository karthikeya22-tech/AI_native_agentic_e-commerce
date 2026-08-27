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
