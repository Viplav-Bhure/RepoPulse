const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL;

export function getApiBaseUrl(): string {
  if (!apiBaseUrl) {
    throw new Error(
      "Missing required environment variable: NEXT_PUBLIC_API_BASE_URL",
    );
  }

  return apiBaseUrl;
}
