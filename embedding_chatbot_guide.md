# AI Chatbot Widget

A lightweight, customizable, and responsive chat widget that can be embedded into any website.

## Features

- Clean, modern UI with smooth animations
- Responsive design that works on all devices
- Real-time typing indicators
- Message history persistence
- Dark mode support
- Customizable appearance
- Easy API integration
- Session management

## Quick Start

### 1. Include the Script

Add the following script tag to your HTML file before the closing `</body>` tag:

```html
<script src="https://chatbot-widget-khaki.vercel.app/chatbot-widget.js"></script>
```

### 2. Initialize the Widget

Add the following script to initialize the widget with the required parameters:

```html
<script>
  document.addEventListener("DOMContentLoaded", function() {
    ChatbotWidget.init({
      businessId: 'YOUR_BUSINESS_ID',        // Required: Your business ID
      botName: 'Your Bot Name',              // Required: Name of your chatbot assistant
      
    });
  });
</script>
```

## Configuration Options

The `ChatbotWidget.init()` function accepts the following parameters:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `businessId` | String | Yes | Your unique business identifier |
| `botName` | String | Yes | The name displayed for your chatbot |
| `initialMessage` | String | Yes | The first message displayed when a user starts a new conversation |
| `botAvatar` | String | No | URL to your bot's avatar image (default: placeholder) |
| `sessionKey` | String | No | Custom session identifier (auto-generated if not provided) |

## Customizing the Widget

You can update the widget's configuration at any time using:

```javascript
ChatbotWidget.updateConfig({
  botName: 'New Bot Name',
  botAvatar: 'https://example.com/new-avatar.jpg'
});
```

## API Integration

The widget connects to your API endpoint configured in the script. The default endpoint is `https://cleaningbizai.com/ai_agent/api/chat/`.

### API Request Format

```json
{
  "message": "User's message text",
  "business_id": "YOUR_BUSINESS_ID",
  "session_key": "Generated session key"
}
```

### Expected API Response Format

The API should return a JSON response with one of the following fields containing the bot's reply:

```json
{
  "response": "Bot's response message"
}
```

Alternative response fields that will be recognized: `reply`, `message`, `answer`, `text`, or `content`.

## Browser Compatibility

- Chrome (latest)
- Firefox (latest)
- Safari (latest)
- Edge (latest)
- Mobile browsers (iOS Safari, Android Chrome)

## Troubleshooting

If the widget doesn't appear:

1. Check browser console for errors
2. Verify that all required parameters are provided
3. Ensure the script is loaded correctly
4. Check if there are any CSS conflicts with your website

For detailed debugging, open your browser's developer console to view logs.

## License

[MIT License](LICENSE) 
