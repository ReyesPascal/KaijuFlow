# A cloned soft voice on Pocket TTS is the best local alert voice; Kokoro is the safe stock voice

The alert voice can sound much more human than Piper without leaving the laptop. Of the free local engines, the best fit is **Kyutai's Pocket TTS**. It was built to run on a CPU. It ships as a standalone Linux binary, as Piper does. It copies the voice of any short wav clip you give it. Feed it a soft, whispered clip and the alert should come out in that voice and, very likely, in that soft delivery ([Pocket TTS README](https://github.com/kyutai-labs/pocket-tts)). The safest stock voice is **Kokoro-82M**, voice `af_heart` (grade A) or `af_bella` (A-). It is the best-graded small model, but it has no whisper or style control ([Kokoro model card](https://huggingface.co/hexgrad/Kokoro-82M); [VOICES.md](https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md)). For an explicit whisper without cloning, **Parler-TTS mini-expresso** has a trained `whisper` style and two female speakers ([model card](https://huggingface.co/parler-tts/parler-tts-mini-expresso)), but expect it to be less natural than the first two. If cloud is acceptable, **ElevenLabs v3** with its `[whispers]` tag is the strongest whisper option ([v3 prompting guide](https://elevenlabs.io/docs/best-practices/prompting/eleven-v3)).

Nobody could listen to audio while researching this. "Realism" below means each project's own claims, plus the links under [Listen before choosing](#listen-before-choosing) so the owner can judge by ear. Speeds for this laptop (i7-1185G7, 4 cores, no GPU) are estimates unless a source gives them. The owner is willing to install things, so pip, uv, Docker and model downloads all count as fine routes. Each section says what the install takes.

## Short answer

1. **Pocket TTS plus a soft reference clip (top pick).** It is small (100M parameters) and runs on 2 CPU cores at about 6x real time on a MacBook Air M4. It supports Python 3.10 to 3.14 and also ships a Rust binary that needs no Python. Its `--voice` option accepts any wav file to clone ([README](https://github.com/kyutai-labs/pocket-tts)). Kyutai's own voice repository has 10-second whisper, calm and sleepy clips from the Expresso dataset of studio actors ([tts-voices](https://huggingface.co/kyutai/tts-voices)). It drops into kf-alert as one command that writes a wav. Risks: whether a whisper clip really yields a whispered alert is unverified, and cloning needs a free Hugging Face login (details below).
2. **Kokoro-82M, `af_heart` (safe second choice).** Apache-2.0, 82M parameters, 54 voices. The author claims "comparable quality to larger models" ([model card](https://huggingface.co/hexgrad/Kokoro-82M)). It has no whisper, but calm voices, a speed setting and voice blending (for example `af_bella(2)+af_sky(1)`) ([Kokoro-FastAPI](https://github.com/remsky/Kokoro-FastAPI)) can make it gentle. The easiest install is the CPU Docker image.
3. **Parler-TTS mini-expresso (whisper by description).** 0.6B parameters, Apache-2.0. You write a sentence describing the delivery, such as "Talia speaks slowly in a whisper". Its styles include `whisper`, and its female speakers are Talia and Elisabeth ([model card](https://huggingface.co/parler-tts/parler-tts-mini-expresso)). It is slower on a CPU, and its naturalness is unverified.

Cloud fallback: ElevenLabs v3 `[whispers]`. A few hundred short sentences a month fit the $6 Starter plan's 30,000 credits ([pricing](https://elevenlabs.io/pricing)). The message text leaves the machine.

## Comparison

"Est." marks a rough estimate for this laptop that no source states. A few seconds is fine here, because kf-alert renders the wav once per alert.

| Engine | Realism (source's own claim) | Soft / whisper control | One sentence on this CPU | Size | Licence | Install route |
|---|---|---|---|---|---|---|
| **Piper** (now) | Fast, local; no realism claim | None. Only speed (`--length_scale`) and noise knobs | Under 1 s (est.) | 63 MB medium, 114 MB high | Engine GPL-3.0 (piper1-gpl); voices vary | Already installed |
| **Pocket TTS** | "High-quality TTS with voice cloning that runs on CPU" | Clone a whisper or calm clip | About 6x real time on 2 cores (M4); est. 1–3 s plus model load | 100M params | Code MIT; weights CC BY 4.0, gated | Rust binary (no Python), `uvx`, pip, or Docker |
| **Kokoro-82M** | "Comparable quality to larger models"; voices graded A to D | None; speed and voice blending | Est. 1–3 s | About 300 MB, or 80 MB quantized (ONNX) | Apache-2.0 | CPU Docker image, or `kokoro-onnx` via uv |
| **Parler-TTS mini-expresso** | No benchmark on its card | `whisper` style by text description | Est. 10–40 s | 0.6B | Apache-2.0 | pip from git, via uv |
| **Chatterbox** (Nano/Turbo/original) | Podonos comparisons vs ElevenLabs (results not on README) | Clone a soft clip; `exaggeration`; tags like `[laugh]` | Nano 3x real time on 8 cores; original est. 30 s to minutes | 110M / 350M / 500M | MIT; watermarked; **retired Aug 2026** | `pip install chatterbox-tts`, Python 3.11 via uv |
| **NeuTTS Air / Nano** | "Best-in-class realism for their size" | Clone a clip (3–15 s) | Real time on mid-range CPUs (claimed) | 360M / 120M | Air Apache-2.0; Nano own licence; watermarked | `pip install neutts[all]` |
| **XTTS-v2** | "Better prosody and audio quality"; no benchmark | Clone a 6 s clip | Est. 10–60 s | Not stated | CPML (non-commercial) | `coqui-tts` fork, Python 3.10–3.14 |
| **F5-TTS** | Demo page only | Clone a clip | No CPU path documented; est. slow | Not checked | Weights CC-BY-NC | pip or Docker |
| **StyleTTS2** | "First human-level TTS" on LJSpeech and VCTK | Reference-audio style | Not documented | Not checked | Code MIT; must disclose synthetic voice | Clone repo; mostly unmaintained |
| **Orpheus 3B** | "Superior to SOTA closed source models" | Tags like `<sigh>`; no whisper tag | `orpheus-cpp` CPU path; est. tens of s to minutes | 3B | Apache-2.0; gated | pip, llama.cpp |
| **Maya1** | Promotional only | `<whisper>` tag plus voice description | 16 GB+ GPU recommended; CPU impractical (est.) | 3.3B | Apache-2.0 | pip |
| **Qwen3-TTS VoiceDesign** | Low WER on Seed-TTS | Voice from text description (whisper not confirmed) | Examples are GPU-only; est. slow | 1.7B | Apache-2.0 | `pip install qwen-tts`, Python 3.12 |
| **Zonos** | "On par with... top TTS providers" | Emotions; whisper via audio prefix | "Much slower" on CPU | Not stated | Apache-2.0 | Docker compose (GPU) |
| **Dia 1.6B** | Compared with ElevenLabs on a demo page | Tags incl. `(sighs)`, `(inhales)`; no whisper | "CPU support is to be added soon" | 1.6B | Apache-2.0 | Needs GPU |
| **Sesame CSM-1B** | Best with context | Context audio | CUDA GPU required | 1B | Apache-2.0; gated | Needs GPU |
| **MeloTTS / OpenVoice** | "CPU real-time" (Melo) | OpenVoice claims emotion and style control | Fast (Melo) | Not checked | MIT | pip; older stack |
| **ElevenLabs v3** (cloud) | Market leader (not verified) | `[whispers]`, descriptive tags | Network call | n/a | Paid; Starter $6 for 30k credits | API key, curl |
| **OpenAI gpt-4o-mini-tts** (cloud) | n/a | `instructions` can ask for whispering | Network call | n/a | $0.60/1M text tokens, $12/1M audio tokens; **shuts down Jan 6, 2027** | API key, curl |
| **Azure Dragon HD** (cloud) | n/a | `whispering` style; `styledegree` | Network call | n/a | Free tier 0.5M neural chars/month | Azure account |
| **Gemini Flash TTS** (cloud) | n/a | Style text, e.g. "whispered urgently"; "Breathy" and "Soft" voices | Network call | n/a | $0.50 text / $9 audio per 1M tokens to Dec 31, 2026 | API key |

## Each candidate

### Piper (what kf-alert uses now)

The original `rhasspy/piper` repository was archived on Oct 6, 2025, and development moved to `OHF-Voice/piper1-gpl` ([rhasspy/piper](https://github.com/rhasspy/piper); [piper1-gpl](https://github.com/OHF-Voice/piper1-gpl)). The installed 2023.11.14-2 binary still works.

- **Higher-quality voices.** The voice index lists five "high" English models: `en_US-lessac-high`, `en_US-ljspeech-high`, `en_GB-cori-high`, `en_US-ryan-high` (male) and `en_US-libritts-high`, which has 904 speakers ([voices.json](https://huggingface.co/rhasspy/piper-voices/blob/main/voices.json)). "High" means 22.05 kHz and 28–32M parameters ([samples page](https://rhasspy.github.io/piper-samples/)). Lessac, LJSpeech and Cori are female readers, based on general knowledge of those datasets rather than the voice index. `en_GB-semaine-medium` has 4 speakers from an emotional-dialogue corpus. These are all VITS models, the same kind already installed. "High" is cleaner, not more human.
- **Can it be softer?** Only a little. The binary takes `--length_scale` (slower), `--noise_scale` and `--noise_w` (variation), `--sentence_silence` and `--speaker` ([main.cpp flags](https://github.com/rhasspy/piper/blob/master/src/cpp/main.cpp)). The installed jenny model's defaults are `noise_scale 0.667`, `noise_w 0.8` (read from the local `.onnx.json`). Piper has no style or whisper input. The newer CLI adds `--volume` ([CLI.md](https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/CLI.md)), but quieter is not breathier.
- **Verdict.** Trying `en_US-libritts-high` speakers or `en_GB-cori-high` costs about 114–137 MB and no new software. It will not reach "soft and human".

### Pocket TTS (Kyutai), top pick

- **Realism.** Kyutai calls it "a high-quality TTS with voice cloning that runs on CPU" (tech report, Jan 2026). It has been retrained twice since, with "drifting" (Sep 2026) and with small 2M–18M models (Oct 2026) ([README](https://github.com/kyutai-labs/pocket-tts)). The model card gives no MOS or Elo numbers ([model card](https://huggingface.co/kyutai/pocket-tts)). A secondary report of a blind test run by a vendor (Gradium) puts Pocket TTS at 2,056 Elo against Kokoro's 2,043. It is not a primary source; treat it as a tie ([search summary of itechguides](https://www.itechguides.com/phonon-vs-other-open-source-text-to-speech-models-for-local-apps/), unverified).
- **Soft or whisper.** There is no style knob. Style comes from the clip you clone. The README warns that "the audio quality of the sample is also reproduced", which implies the delivery carries over as well. That implication is unverified for whisper. Kyutai's voice repo has 10-second clips (960 KB at 48 kHz) in the styles `whisper`, `calm`, `sleepy` and `desire` ([tts-voices file list](https://huggingface.co/kyutai/tts-voices/tree/main/expresso)):
  - `expresso/ex04-ex03_whisper_001_channel1_198s.wav` and `expresso/ex04-ex03_whisper_002_channel2_266s.wav`
  - `expresso/ex01-ex02_whisper_001_channel1_579s.wav` and `..._channel2_717s.wav`
  - `expresso/ex03-ex01_calm_001_channel1_1143s.wav`, `expresso/ex04-ex02_calm_002_channel1_480s.wav`, plus `sleepy` and `desire` clips

  Expresso has two male and two female speakers but does not say which ID is which ([Expresso](https://speechbot.github.io/expresso/)). Kyutai's female preset `cosette` is cloned from `ex04-ex02_..._channel1` ([README](https://github.com/kyutai-labs/pocket-tts)). That hints that ex04 is female, but it is an inference, so listen to each clip first.
- **CPU.** About 200 ms to first audio and about 6x real time on an M4 using 2 cores. On a 4-vCPU cloud x86 machine it ran at 2.3–2.5x real time ([README](https://github.com/kyutai-labs/pocket-tts)). A 4-second alert should take one to two seconds plus model loading here (est.). The laptop's CPU has AVX2, which the binary needs (checked in `/proc/cpuinfo`).
- **Licence and consent.** Code MIT. Weights CC BY 4.0. The voice-cloning repo `kyutai/pocket-tts` is gated (accept terms; approval is automatic), while `kyutai/pocket-tts-without-voice-cloning` is not ([HF API](https://huggingface.co/api/models/kyutai/pocket-tts)). The terms forbid cloning a voice without "explicit, lawful consent". Expresso clips are CC BY-NC 4.0, which allows personal use. Do not clone a YouTube ASMR creator or any other real person without their permission.
- **Install.** Choose one:
  - Rust binary: the Linux x86_64 tarball on [Releases](https://github.com/kyutai-labs/pocket-tts/releases) is about 8.6 MB, with no Python or PyTorch.
  - `uvx --index https://download.pytorch.org/whl/cpu pocket-tts generate`. The CPU index avoids about 3 GB of CUDA wheels.
  - Docker: the repo has a Dockerfile and compose file.
  - Weights download to the Hugging Face cache on first use.
- **Into kf-alert.** `pocket-tts generate -q --text "…" --voice ~/.local/share/kf-voice/soft.safetensors --output-path "$wav"`.

### Kokoro-82M

- **Realism.** "Comparable quality to larger models while being significantly faster and more cost-efficient" ([model card](https://huggingface.co/hexgrad/Kokoro-82M)). The author grades each voice. US female: `af_heart` A, `af_bella` A-, `af_nicole` B-, `af_aoede`, `af_kore` and `af_sarah` C+. UK female: `bf_emma` B- ([VOICES.md](https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md)). `af_nicole` is commonly described as a whispery voice, but the official list does not say so (unverified).
- **Soft or whisper.** No style input and no cloning. You can lower the speed and blend voices with weights ([Kokoro-FastAPI](https://github.com/remsky/Kokoro-FastAPI)).
- **CPU.** Kokoro-FastAPI reports about 3.5 s to first audio on "an older i7" with 200-character chunks ([Kokoro-FastAPI](https://github.com/remsky/Kokoro-FastAPI)). One sentence should take a few seconds (est.).
- **Install.**
  - Docker: `docker run -p 8880:8880 ghcr.io/remsky/kokoro-fastapi-cpu:v0.10.0`. v0.10.0 is the latest release (Nov 8, 2026); pin it rather than `:latest`. The server is OpenAI-compatible at `/v1/audio/speech`.
  - No Docker: `kokoro-onnx` is MIT and its badges list Python 3.10–3.13, so run it through `uv` with Python 3.12 rather than the system 3.14 ([kokoro-onnx](https://github.com/thewh1teagle/kokoro-onnx)).
- **Into kf-alert.** `curl -s localhost:8880/v1/audio/speech -H 'Content-Type: application/json' -d '{"model":"kokoro","voice":"af_heart","input":"…","response_format":"wav","speed":0.9}' -o "$wav"`. This needs the container running; `docker run --restart unless-stopped` keeps it up.

### Parler-TTS mini-expresso

- **Realism.** The card gives no benchmark. The base Parler models are 880M (mini) and 2.3B (large) ([parler-tts](https://github.com/huggingface/parler-tts)).
- **Soft or whisper.** This is the only CPU-feasible local model with whisper as a trained style. The styles are happy, confused, default, laughing, sad, whisper and emphasis. The female speakers are Talia and Elisabeth ([model card](https://huggingface.co/parler-tts/parler-tts-mini-expresso)). The card's pattern is "<Name> speaks <pace> in a <style> tone … high quality audio".
- **CPU.** The sample code falls back to CPU; no speed is given. With 0.6B parameters, 10–40 s per sentence is plausible (est.).
- **Install.** `pip install git+https://github.com/huggingface/parler-tts.git` inside a `uv` environment on Python 3.11 or 3.12. The 3.14 support of the pinned transformers version is unverified. You also need a 10-line Python script that writes the wav.

### Chatterbox (Resemble AI)

- **Status.** "As of August 2026, Chatterbox is retired research and is no longer maintained" ([README](https://github.com/resemble-ai/chatterbox)). The code still works under MIT.
- **Variants.** Nano 110M ("3x faster than realtime on 8 CPU cores"), Turbo 350M and the original 500M ([README](https://github.com/resemble-ai/chatterbox); [Nano card](https://huggingface.co/ResembleAI/chatterbox-nano)).
- **Soft or whisper.** Clone a reference clip (about 10 s). On the original model, a lower `exaggeration` is calmer, and `cfg_weight` around 0.3 slows the pace. Turbo and Nano take tags like `[laugh]` and `[chuckle]`; the README names no whisper tag.
- **Other notes.** Every output carries Resemble's inaudible Perth watermark. It was tested on Python 3.11, so use `uv`.
- **Realism.** The README links Podonos comparisons of Turbo against ElevenLabs Turbo v2.5 but does not quote the results. A third-party blog claims "65.3% beats ElevenLabs" (unverified).
- **Verdict.** A good second engine for the same cloning idea as Pocket TTS, but it is no longer maintained.

### NeuTTS (Neuphonic)

- **Facts.** Air has about 360M active parameters and an Apache-2.0 licence. Nano has about 120M and Neuphonic's own licence. Both clone from a 3–15 s clean mono wav. They ship as GGUF quantisations for llama.cpp, and every file is Perth-watermarked ([README](https://github.com/neuphonic/neutts-air)).
- **Realism.** They claim "Best-in-class realism for their size" and real-time generation on mid-range devices.
- **Install.** `pip install "neutts[all]"`; no Python version is stated.
- **Verdict.** The same cloning approach as Pocket TTS, with a heavier install.

### Coqui XTTS-v2

- **Facts.** Clones from "a quick 6-second audio clip" and covers 17 languages. The CPML licence is non-commercial, which is fine for personal use ([model card](https://huggingface.co/coqui/XTTS-v2)).
- **Status and install.** Coqui shut down. The maintained fork is `coqui-tts` (Idiap), which supports Python 3.10 to 3.14 ([fork README](https://github.com/idiap/coqui-ai-TTS)).
- **Speed and quality.** The examples assume a GPU. CPU runs are slow (10–60 s, est.). Quality is good, but it is a 2023 model that newer ones have passed.

### F5-TTS

- **Facts.** Code is MIT; weights are CC-BY-NC because of the Emilia training data. It clones from a reference clip with `f5-tts_infer-cli --ref_audio … --ref_text … --gen_text …`. A Docker image exists (`ghcr.io/swivid/f5-tts:main`) ([README](https://github.com/SWivid/F5-TTS)).
- **Verdict.** No CPU path is documented, so expect it to be slow. Its demo page is worth a listen.

### StyleTTS2

- **Claims.** "The first human-level TTS synthesis on both single and multispeaker datasets" ([README](https://github.com/yl4579/StyleTTS2)).
- **Licence.** Pretrained-model use requires telling listeners the speech is synthetic unless you have permission for the voice.
- **Verdict.** 104 open issues, and inference depends on a GPL package that is not included. Fiddly to set up. Its samples are on [styletts2.github.io](https://styletts2.github.io/).

### Orpheus 3B (Canopy Labs)

- **Facts.** A Llama-3B backbone with voices tara, leah, jess, leo, dan, mia, zac and zoe. The repo does not state genders. Tags are `<laugh> <chuckle> <sigh> <cough> <sniffle> <groan> <yawn> <gasp>`; there is no whisper tag. The authors claim it is "superior to SOTA closed source models" ([README](https://github.com/canopyai/Orpheus-TTS)). The weights are gated ([card](https://huggingface.co/canopylabs/orpheus-3b-0.1-ft)).
- **CPU.** A CPU route exists through `pip install orpheus-cpp` plus `llama-cpp-python` ([no-GPU guide](https://github.com/canopyai/Orpheus-TTS/tree/main/additional_inference_options/no_gpu)), but no speeds are given. A 3B model on 4 cores will likely take tens of seconds to minutes per sentence (est.).
- **Verdict.** A borderline fit for this laptop.

### Maya1, Qwen3-TTS, Zonos, Dia, Sesame CSM: strong but GPU-shaped

- **Maya1** (3.3B, Apache-2.0). It is the most on-target for ASMR: it takes a written voice description plus a `<whisper>` tag. But it recommends a GPU with 16 GB+ of VRAM ([card](https://huggingface.co/maya-research/maya1)).
- **Qwen3-TTS VoiceDesign** (1.7B, Apache-2.0). It makes a voice from a text description and clones from 3 s. Its examples use `cuda:0` and recommend Python 3.12 ([repo](https://github.com/QwenLM/Qwen3-TTS)). Whisper prompts are not shown.
- **Zonos** (Apache-2.0). It has happiness, anger, sadness and fear controls and notes that audio prefixes can elicit whispering. It wants a GPU with 6 GB+, and on a CPU it is "much slower" ([repo](https://github.com/Zyphra/Zonos)).
- **Dia** (1.6B). "CPU support is to be added soon." Its tags include `(inhales)` and `(exhales)` but no whisper ([repo](https://github.com/nari-labs/dia)). Dia2 exists but was not checked.
- **Sesame CSM-1B.** It needs a CUDA GPU and has no fixed voices ([repo](https://github.com/SesameAILabs/csm)).

None of these is a sensible CPU-only pick today.

### MeloTTS and OpenVoice

- **Facts.** Both are MIT. MeloTTS is "fast enough for CPU real-time inference" and has American, British, Indian and Australian English voices, with no style controls ([MeloTTS](https://github.com/myshell-ai/MeloTTS)). OpenVoice V2 claims "granular control over voice styles", including emotion and accent ([OpenVoice](https://github.com/myshell-ai/OpenVoice)).
- **Verdict.** It is a 2024 stack, now passed by Pocket TTS and Kokoro.

### Cloud fallbacks (the message text leaves the machine)

Assume about 300 sentences a month at 60–120 characters, which is about 20,000–36,000 characters and about 25 minutes of audio.

- **ElevenLabs.**
  - Style: v3 supports `[whispers]` and descriptive bracket tags like `[Softly, with wonder]`. Voices that already whisper in their training data follow the tag best ([v3 prompting](https://elevenlabs.io/docs/best-practices/prompting/eleven-v3)).
  - Cost: Free is 10,000 credits a month and Starter is $6 for 30,000. Multilingual v2 costs 1 credit per character; the page does not state v3's rate ([pricing](https://elevenlabs.io/pricing)). So Starter covers the load, and Free covers about a third.
  - Best realism and whisper of the cloud options, though this is the general reputation, not verified here.
- **OpenAI `gpt-4o-mini-tts`.**
  - Style: an `instructions` field controls tone, and the docs list whispering among what prompts can control. It returns wav directly. Users must be told the voice is AI-generated ([TTS guide](https://developers.openai.com/api/docs/guides/text-to-speech)).
  - Cost: $0.60 per 1M text tokens and $12 per 1M audio tokens ([pricing](https://developers.openai.com/api/docs/pricing)), likely well under $1 a month for this load (est.).
  - **It shuts down on January 6, 2027**, so do not build on it.
- **Azure Speech.**
  - Style: Dragon HD voices accept `[whispering]` or `<mstts:express-as style="whispering">` on all English voices. Older neural voices describe `whispering` as "a soft tone that's trying to make a quiet and gentle sound", with `styledegree` from 0.01 to 2 ([SSML docs](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/speech-synthesis-markup-voice)).
  - Cost: the free tier gives 0.5M neural characters a month, well above this load. The pricing page showed no HD rates ([pricing](https://azure.microsoft.com/en-us/pricing/details/speech/)).
- **Google Gemini TTS.**
  - Style: a free-text style field (the docs' example is "whispered urgently") and voices tagged *Breathy* (Enceladus) and *Soft* (Achernar) ([speech docs](https://aistudio.google.com/docs/speech-generation)). The voices' genders were not checked.
  - Cost: Gemini 3.8 Flash TTS is $0.50 text / $9 audio per 1M tokens until Dec 31, 2026, then double. The free tier exists, but free-tier data is used to improve Google's products ([pricing](https://aistudio.google.com/docs/pricing)).

## Listen before choosing

- Pocket TTS in the browser, with your own wav clip: [kyutai.org/pocket-tts](https://kyutai.org/pocket-tts).
- The Expresso whisper and calm clips to clone (click a file, then play): [kyutai/tts-voices/expresso](https://huggingface.co/kyutai/tts-voices/tree/main/expresso). Start with `ex04-ex03_whisper_001_channel1_198s.wav`.
- Pocket TTS preset voices (female by naming: anna, azelma, cosette, eponine, eve, fantine, jane, mary, vera, alba): the links in the [README voice list](https://github.com/kyutai-labs/pocket-tts#the-generate-command).
- Kokoro in the browser: [Kokoro-TTS Space](https://huggingface.co/spaces/hexgrad/Kokoro-TTS). Try `af_heart`, `af_bella` and `af_nicole`.
- Piper's high voices: [Piper samples](https://rhasspy.github.io/piper-samples/). Pick `en_US-libritts-high`, `en_GB-cori-high` and `en_US-lessac-high`.
- Parler whisper: [Parler-TTS Space](https://huggingface.co/spaces/parler-tts/parler_tts). The expresso checkpoint may need its own Space or a local run.
- Chatterbox: [demo page](https://resemble-ai.github.io/chatterbox_demopage/), [Turbo demo page](https://resemble-ai.github.io/chatterbox_turbo_demopage/).
- NeuTTS Air: [Space](https://huggingface.co/spaces/neuphonic/neutts-air).
- F5-TTS: [demo page](https://swivid.github.io/F5-TTS/). StyleTTS2: [samples](https://styletts2.github.io/). XTTS: [Space](https://huggingface.co/spaces/coqui/xtts). Maya1: [Space](https://huggingface.co/spaces/maya-research/maya1). Zonos: [playground](https://playground.zyphra.com/audio).
- Cloud: the ElevenLabs voice library, filtered for "whisper" or "ASMR" (needs an account), and Azure's Speech Studio voice gallery.

## How to try the top pick (commands, not run)

These steps install Pocket TTS's standalone binary, clone a soft clip and test it, all without touching kf-alert.

```bash
# 1. Binary (about 8.6 MB). Check the exact asset name on the Releases page.
mkdir -p ~/.local/share/pocket-tts && cd ~/.local/share/pocket-tts
curl -LO https://github.com/kyutai-labs/pocket-tts/releases/download/v4.0.1/pocket-tts-3.3.0-x86_64-unknown-linux-gnu.tar.gz
tar xzf pocket-tts-*.tar.gz
PT=$(ls -d ~/.local/share/pocket-tts/pocket-tts-*/)pocket-tts

# 2. Smoke test with a stock voice (ungated weights; downloads to the HF cache on first run).
"$PT" generate --voice vera --text "Hey you. Kaiju Flow needs you." --output-path /tmp/t1.wav && pw-play /tmp/t1.wav

# 3. Voice cloning needs the gated repo: open https://huggingface.co/kyutai/pocket-tts while logged in,
#    accept the terms, make a read token at https://huggingface.co/settings/tokens, then:
export HF_TOKEN=hf_xxx   # whether the Rust binary reads HF_TOKEN is unverified; `uvx hf auth login` writes the shared cache token

# 4. Turn a whisper clip into a fast-loading voice file. Only the first 30 s are used.
mkdir -p ~/.local/share/kf-voice
"$PT" export-voice hf://kyutai/tts-voices/expresso/ex04-ex03_whisper_001_channel1_198s.wav ~/.local/share/kf-voice/soft.safetensors

# 5. Hear it. Try temperature 0.3 (default) to 0.6, and the calm or sleepy clips if the whisper is too faint.
"$PT" generate -q --voice ~/.local/share/kf-voice/soft.safetensors \
  --text "Hey you. Kaiju Flow needs you. The run finished." --output-path /tmp/t2.wav && pw-play /tmp/t2.wav
```

If the binary misbehaves, the Python route is the same command with `uvx --index https://download.pytorch.org/whl/cpu pocket-tts` in place of `"$PT"`. You would need to install `uv` first ([uv installer](https://docs.astral.sh/uv/getting-started/installation/#standalone-installer)).

**Dropping it into kf-alert.** Replace the Piper block with a Pocket TTS try, and keep Piper and then `spd-say` as fallbacks:

```bash
P=$(ls -d ~/.local/share/pocket-tts/pocket-tts-*/ 2>/dev/null)pocket-tts
V=~/.local/share/kf-voice/soft.safetensors
if [ -x "$P" ] && [ -f "$V" ] &&
   "$P" generate -q --voice "$V" --text "Hey you. Kaiju Flow needs you. $msg" --output-path "$wav" >/dev/null 2>&1; then
  say() { pw-play "$wav" & s=$!; }
elif [ -x "$D/bin/piper/piper" ] && ...   # existing Piper line unchanged
```

kf-alert returns at once and renders before the loop starts, so a few seconds of model loading only delays the first playback. If that delay matters, run `pocket-tts serve` as a user service and fetch the wav over HTTP instead ([serve docs](https://kyutai-labs.github.io/pocket-tts/CLI%20Commands/serve/)).

## Not verified

- No audio was heard. Every realism statement is the project's own claim or a secondary report.
- Pocket TTS: whether a whisper clip produces a whispered alert; which Expresso IDs are female; whether the Rust binary reads `HF_TOKEN`.
- Kokoro: that `af_nicole` sounds whispery.
- Parler mini-expresso: its exact prompt wording and its Python 3.14 compatibility.
- All CPU timings marked "est.".
- Cloud: ElevenLabs v3's credit rate per character and the gpt-4o-mini-tts cost per minute.
- Not checked at all: the TTS Arena leaderboard (the page loaded empty), Dia2, VibeVoice, IndexTTS2, Higgs Audio and Kitten TTS.
