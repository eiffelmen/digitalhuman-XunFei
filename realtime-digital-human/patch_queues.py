import os

with open('baseasr.py', 'r', encoding='utf-8') as f: code = f.read()
code = code.replace('"ASR_INPUT_QUEUE_MAX", "250"', '"ASR_INPUT_QUEUE_MAX", "5000"')
code = code.replace('"ASR_OUTPUT_QUEUE_MAX", "250"', '"ASR_OUTPUT_QUEUE_MAX", "5000"')
code = code.replace('self.feat_queue = mp.Queue(2)', 'self.feat_queue = mp.Queue(1000)')
old_put = '''            self.queue.put_nowait(audio_chunk)
        except queue.Full:
            try:
                self.queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self.queue.put_nowait(audio_chunk)
            except queue.Full:
                pass'''
new_put = '''            self.queue.put(audio_chunk, block=True, timeout=2.0)
        except queue.Full:
            pass'''
code = code.replace(old_put, new_put)
old_flush = '''    def flush_talk(self):
        self.queue.queue.clear()'''
new_flush = '''    def flush_talk(self):
        while not self.queue.empty():
            try:
                self.queue.get_nowait()
            except:
                break'''
code = code.replace(old_flush, new_flush)

with open('baseasr.py', 'w', encoding='utf-8') as f: f.write(code)

with open('lipasr.py', 'r', encoding='utf-8') as f: code = f.read()
old_lip_put = '''            target_queue.put_nowait(item)
            return
        except queue.Full:
            pass
        except Exception:
            try:
                target_queue.put(item, block=False)
                return
            except Exception:
                pass

        try:
            target_queue.get_nowait()
        except Exception:
            pass
        try:
            target_queue.put_nowait(item)
        except Exception:
            pass'''
new_lip_put = '''            target_queue.put(item, block=True, timeout=2.0)
        except queue.Full:
            pass
        except Exception:
            pass'''
code = code.replace(old_lip_put, new_lip_put)
with open('lipasr.py', 'w', encoding='utf-8') as f: f.write(code)
print("Patch applied")
