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

    // Add error handling for the AI button
    const aiGenerateBtn = document.getElementById('aiGenerateBtn');
    if (aiGenerateBtn) {
        aiGenerateBtn.addEventListener('click', async () => {
            const promptInput = document.getElementById('aiPrompt');
            const typeSelect = document.getElementById('aiQuestionType');
            const aiInputForm = document.getElementById('aiInputForm');
            const aiLoading = document.getElementById('aiLoading');
            const errorElem = document.querySelector('.ai-error');
            
            if (errorElem) errorElem.remove(); // Clear previous errors
            
            if (!promptInput.value.trim()) {
                const error = document.createElement('div');
                error.className = 'ai-error';
                error.textContent = 'Please enter a prompt for the question';
                aiInputForm.appendChild(error);
                return;
            }
            
            // Show loading state
            aiInputForm.style.display = 'none';
            aiLoading.style.display = 'flex';
            
            try {
                await window.aiConnector.generateQuestion(promptInput.value, typeSelect.value);
            } catch (error) {
                const errorDiv = document.createElement('div');
                errorDiv.className = 'ai-error';
                
                // Provide more specific error messages
                if (error.message.includes("timed out")) {
                    errorDiv.innerHTML = `
                        <strong>Connection Timed Out</strong><br>
                        The request to LM Studio took too long. Please check that:<br>
                        1. LM Studio is running<br>
                        2. The DeepSeek Coder model is loaded<br>
                        3. API server is enabled in LM Studio settings<br>
                        4. Your model isn't too large for your hardware
                    `;
                } else if (error.message.includes("Failed to connect")) {
                    errorDiv.innerHTML = `
                        <strong>Connection Failed</strong><br>
                        Could not connect to LM Studio. Please check that:<br>
                        1. LM Studio is running on localhost:1234<br>
                        2. API server is enabled in LM Studio settings<br>
                        3. The DeepSeek Coder model is loaded
                    `;
                } else {
                    errorDiv.textContent = `Error: ${error.message || 'Failed to generate question'}`;
                }
                
                aiInputForm.appendChild(errorDiv);
                
                // Hide loading, show form again
                aiLoading.style.display = 'none';
                aiInputForm.style.display = 'block';
            }
        });
    }
}); 