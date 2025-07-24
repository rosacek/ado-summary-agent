import os
import json
import re
import logging
import time
import ollama
from .settings import SUMMARY_LENGTH, OLLAMA_MODEL, OLLAMA_HOST

logger = logging.getLogger(__name__)

class Summarizer:
    def __init__(self):
        # Ollama configuration
        self.model_name = OLLAMA_MODEL
        self.host = OLLAMA_HOST
        self.ai_timeout = 900  # 15 minutes
        self.max_length = 120000  # Utilize full Phi-3.5 128k context window
        
        # Initialize Ollama client with optimized settings for Phi-3.5
        self.client = ollama.Client(host=self.host)
        
        # Initialize model
        self._initialize_model()
        
    def _initialize_model(self):
        """Initialize the Ollama model"""
        try:
            logger.info(f"🔄 Initializing Ollama model: {self.model_name}")
            
            # Check if model is available
            models = self.client.list()
            available_models = []
            
            # Handle different response structures
            if hasattr(models, 'models') and models.models:
                available_models = [model.model for model in models.models]
            elif isinstance(models, dict) and 'models' in models:
                available_models = [model.get('model', model.get('name', '')) for model in models['models']]
            
            logger.info(f"Available models: {available_models}")
            
            if self.model_name not in available_models:
                logger.info(f"📦 Model {self.model_name} not found, attempting to pull...")
                self.client.pull(self.model_name)
                logger.info(f"✅ Model {self.model_name} pulled successfully")
            else:
                logger.info(f"✅ Model {self.model_name} already available")
            
            # Test model with a simple prompt
            response = self.client.generate(
                model=self.model_name,
                prompt="Hello, world!",
                stream=False
            )
            
            if response and response.get('response'):
                logger.info("✅ Ollama model initialized and tested successfully")
            else:
                raise RuntimeError("Model test failed - no response received")
                
        except Exception as e:
            logger.error(f"❌ Failed to initialize Ollama model: {str(e)}")
            raise RuntimeError(f"Ollama model initialization failed: {str(e)}")
    
    def is_available(self):
        """Check if the AI model is available"""
        try:
            models = self.client.list()
            available_models = []
            
            # Handle different response structures
            if hasattr(models, 'models') and models.models:
                available_models = [model.model for model in models.models]
            elif isinstance(models, dict) and 'models' in models:
                available_models = [model.get('model', model.get('name', '')) for model in models['models']]
            
            return self.model_name in available_models
        except Exception:
            return False

    def summarize(self, work_item_context):
        """Main entry point - AI processing only"""
        context_size = len(work_item_context)
        logger.info(f"📝 Processing work item context ({context_size} characters) with AI")
        
        return self._generate_ai_summary(work_item_context)

    def _generate_ai_summary(self, context):
        """Generate summary using Ollama"""
        context_size = len(context)
        
        # Truncate context if too long
        if context_size > self.max_length:
            logger.info(f"Context size {context_size} exceeds max_length {self.max_length}, truncating")
            context = context[:self.max_length]
            context_size = len(context)
        
        # Build strict system prompt for deterministic, fact-based output
        system_prompt = """You are a work item analyst. Extract and present ONLY the factual information provided. Do not make assumptions, extrapolate, or add interpretations.

OUTPUT FORMAT (use exact field values from context):

**EXECUTIVE SUMMARY**
Brief description of what this work item addresses based on title and description only.

**KEY DETAILS**
• Work Item ID: [exact ID]
• Type: [exact type]
• State: [exact state] 
• Priority: [exact priority or "Not specified"]
• Business Value: [exact value or "Not specified"]
• Assigned To: [exact name or "Unassigned"]
• Area Path: [exact path]
• Iteration: [exact iteration or "Not specified"]
• Story Points: [exact points or "Not estimated"]

**DESCRIPTION** 
[Copy description text exactly as provided, or "No description provided"]

**ACCEPTANCE CRITERIA**
[List exact criteria from context, or "No acceptance criteria provided"]

**TECHNICAL DETAILS**
[Extract any technical information from description/criteria, or "No technical details provided"]

**NEXT ACTIONS**
[Extract specific actions mentioned, or "No specific actions identified"]

**DEPENDENCIES & RISKS**
[Extract specific dependencies/blockers mentioned, or "No dependencies identified"]

STRICT RULES:
1. Use ONLY information explicitly provided in context
2. Copy field values exactly as they appear
3. If information is missing, state "Not specified/provided"
4. No assumptions, conversions, or extrapolations
5. Keep responses factual and concise"""
        try:
            logger.info(f"🤖 Generating AI summary for {context_size} characters (timeout: {self.ai_timeout}s)")
            # Create messages for chat completion
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": context}
            ]
            
            # Generate response using Ollama with deterministic settings
            start_time = time.time()
            response = self.client.chat(
                model=self.model_name,
                messages=messages,
                stream=False,
                options={
                    "temperature": 0.1,  # Very low for deterministic output
                    "top_p": 0.8,        # Reduced for more focused responses
                    "top_k": 10,         # Much lower for consistency
                    "repeat_penalty": 1.1,  # Minimal to avoid repetition
                    "num_predict": 1200  # Increased for complete sections (was 600)
                }
            )
            
            generation_time = time.time() - start_time
            
            if response and response.get('message', {}).get('content'):
                result = response['message']['content'].strip()
                logger.info(f"✅ AI summary generated successfully ({len(result)} chars, {generation_time:.1f}s)")
                return result
            else:
                raise RuntimeError("No response content received from Ollama")
                
        except Exception as e:
            logger.error(f"❌ AI summary generation failed: {str(e)}")
            # Re-raise exception to trigger retry mechanism in agent
            raise RuntimeError(f"AI summary generation failed: {str(e)}")
