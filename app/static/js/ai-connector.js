/**
 * AI Connector for DeepSeek Coder Model
 * This file handles the communication with the local LM Studio model for code evaluation only
 */

class AIConnector {
    constructor(modelPath) {
        this.modelPath = modelPath || "C:\\Users\\Zyb\\.lmstudio\\models\\bartowski\\DeepSeek-Coder-V2-Lite-Instruct-GGUF\\DeepSeek-Coder-V2-Lite-Instruct-Q8_0_L.gguf";
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
     * Evaluate code with AI and return evaluation result
     * @param {string} codeAnswer - Student's code answer
     * @param {string} questionText - The coding question text
     * @returns {Promise<object>} - Evaluation result with score and feedback
     */
    async evaluateCode(codeAnswer, questionText) {
        if (!this.isReady) {
            await this.initialize();
        }

        console.log(`Evaluating code for question: ${questionText.substring(0, 50)}...`);
        
        // Send the request to our server endpoint which will handle AI evaluation
        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), this.requestTimeout);
            
            const response = await fetch('/form/evaluate-code', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    code_answer: codeAnswer,
                    question_text: questionText,
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

            console.log("AI code evaluation result:", data);
            return data;
        } catch (error) {
            console.error("Error evaluating code:", error);
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
});
