/**
 * AI Connector for DeepSeek Coder Model
 * This file handles the communication with the local LM Studio model
 */

class AIConnector {
    constructor(modelPath) {
        this.modelPath = modelPath || "C:\\Users\\Zyb\\.lmstudio\\models\\LoneStriker\\deepseek-coder-7b-instruct-v1.5-GGUF\\deepseek-coder-7b-instruct-v1.5-Q5_K_M.gguf";
        this.isReady = false;
        this.isLocalModelAvailable = false;
        this.lmStudioEndpoint = "http://localhost:1234/v1/completions"; // Using the confirmed working endpoint
        this.requestTimeout = 90000; // 90 seconds timeout for requests
    }

    /**
     * Initialize the connection to the AI model
     * In a full implementation, this would connect to LM Studio's API
     */
    async initialize() {
        console.log("Initializing AI Connector for DeepSeek Coder model");
        console.log("Model path:", this.modelPath);
        console.log("LM Studio endpoint:", this.lmStudioEndpoint);
        
        // Test connection to LM Studio with timeout
        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), this.requestTimeout);
            
            const response = await fetch('/form/test-lm-studio', {
                method: 'GET',
                signal: controller.signal
            });
            
            clearTimeout(timeoutId);
            
            if (response.ok) {
                const data = await response.json();
                this.isReady = data.success;
                console.log("LM Studio connection test:", data.success ? "SUCCESS" : "FAILED");
                if (!data.success) {
                    console.error("LM Studio connection error:", data.error);
                }
            } else {
                console.error("Failed to test LM Studio connection");
                this.isReady = false;
            }
        } catch (error) {
            console.error("Error testing LM Studio connection:", error);
            this.isReady = false;
            if (error.name === 'AbortError') {
                console.error("Request timed out - LM Studio may be busy processing a large model");
            }
        }
        
        return this.isReady;
    }

    /**
     * Generate a question based on the prompt and type
     * @param {string} prompt - User prompt for the question
     * @param {string} questionType - Type of question (multiple_choice, identification, coding)
     * @returns {Promise<object>} - Generated question data
     */
    async generateQuestion(prompt, questionType) {
        if (!this.isReady) {
            await this.initialize();
        }

        console.log(`Generating ${questionType} question about: ${prompt}`);
        
        // Send the request to our server endpoint which will proxy to LM Studio
        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), this.requestTimeout);
            
            const response = await fetch('/form/ai-question', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    prompt: prompt,
                    question_type: questionType,
                }),
                signal: controller.signal
            });
            
            clearTimeout(timeoutId);

            let data;
            const contentType = response.headers.get('content-type');
            
            if (contentType && contentType.includes('application/json')) {
                data = await response.json();
            } else {
                const text = await response.text();
                throw new Error(`API returned non-JSON response: ${text}`);
            }

            if (!response.ok) {
                throw new Error(`API error: ${response.status} - ${data.error || 'Unknown error'}`);
            }

            console.log("AI generated question:", data);
            return data;
        } catch (error) {
            console.error("Error generating question:", error);
            if (error.name === 'AbortError') {
                throw new Error("The request timed out. LM Studio may be busy processing a large model. Try again or use a smaller model.");
            }
            throw error;
        }
    }
}

// Create a global instance
window.aiConnector = new AIConnector();

// Initialize when the page loads
document.addEventListener('DOMContentLoaded', () => {
    window.aiConnector.initialize()
        .then(() => console.log("AI Connector initialized successfully"))
        .catch(error => console.error("Error initializing AI Connector:", error));

    // Note: Event listener for aiGenerateBtn is handled in edit_form.html
    // to avoid duplicate event handlers that cause multiple requests
}); 