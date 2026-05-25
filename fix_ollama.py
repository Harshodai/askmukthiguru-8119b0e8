#!/usr/bin/env python3
import re

path = 'backend/services/ollama_service.py'
content = open(path).read()

# ---- Fix generate() ----
# Find the try block inside generate()
gen_start = content.find('        try:\n            # Bind runtime args like temperature')
gen_end_block = content.find('        except Exception as e:\n            logger.error(f"Ollama generation failed: {e}")\n            raise')

if gen_start == -1 or gen_end_block == -1:
    print(f"ERROR: generate() block not found ({gen_start}, {gen_end_block})")
else:
    new_block = '''        # Extract timeout from kwargs (pop so it's not passed to bind())
        timeout = kwargs.pop("timeout", settings.llm_timeout)
        max_retries = kwargs.pop("max_retries", 1)
        last_err = None
        for attempt in range(max_retries):
            try:
                chain = self._llm.bind(**kwargs) if kwargs else self._llm
                response = await asyncio.wait_for(chain.ainvoke(messages), timeout=timeout)
                content = response.content.strip()
                # Strip ", content, flags=re.DOTALL)
                content_outside_think = re.sub(
                    r"", "", content, flags=re.DOTALL
                ).strip()

                if content_outside_think:
                    content = content_outside_think
                elif think_match:
                    content = think_match.group(1).strip()
                else:
                    content = content.strip()
                return content
            except asyncio.TimeoutError as e:
                last_err = f"Ollama generate timeout after {timeout}s (attempt {attempt+1}/{max_retries})"
                logger.warning(last_err)
                if attempt < max_retries - 1:
                    await asyncio.sleep(0.5 * (attempt + 1))
            except Exception as e:
                logger.error(f"Ollama generation failed: {e}")
                raise
        raise TimeoutError(f"All {max_retries} retries exhausted after {timeout}s") from last_err'''

    old_block = content[gen_start:gen_end_block]
    content = content.replace(old_block, new_block, 1)
    print("generate() fixed")

# ---- Fix _generate_fast() ----
fast_try = content.find('        try:\n            chain = self._llm_fast.bind(**kwargs) if kwargs else self._llm_fast\n            response = await chain.ainvoke(messages)')
fast_except = content.find('        except Exception as e:\n            # Fall back to main model if fast model fails')

if fast_try == -1 or fast_except == -1:
    print(f"ERROR: _generate_fast() block not found ({fast_try}, {fast_except})")
else:
    new_fast_block = '''        _FAST_TIMEOUT = 25
        _FAST_RETRIES = 2
        timeout = kwargs.pop("timeout", _FAST_TIMEOUT)
        max_retries = kwargs.pop("max_retries", _FAST_RETRIES)
        last_err = None
        for attempt in range(max_retries):
            try:
                chain = self._llm_fast.bind(**kwargs) if kwargs else self._llm_fast
                response = await asyncio.wait_for(chain.ainvoke(messages), timeout=timeout)
                content = response.content.strip()
                import re

                think_match = re.search(r"", content, flags=re.DOTALL)
                content_outside_think = re.sub(
                    r"", "", content, flags=re.DOTALL
                ).strip()

                if content_outside_think:
                    content = content_outside_think
                elif think_match:
                    content = think_match.group(1).strip()
                else:
                    content = content.strip()
                return content
            except asyncio.TimeoutError as e:
                last_err = f"Ollama _generate_fast timeout after {timeout}s (attempt {attempt+1}/{max_retries})"
                logger.warning(last_err)
                if attempt < max_retries - 1:
                    await asyncio.sleep(0.5 * (attempt + 1))
            except Exception as e:
                logger.warning(f"Fast model failed: {e}, falling back to main model")
                return await self.generate(system_prompt, user_prompt, **kwargs)
        logger.warning(f"Fast model retries exhausted, falling back to main model")
        return await self.generate(system_prompt, user_prompt, **kwargs)'''

    old_fast_block = content[fast_try:fast_except]
    content = content.replace(old_fast_block, new_fast_block, 1)
    print("_generate_fast() fixed")

open(path, 'w').write(content)
print("File written successfully")