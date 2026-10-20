"""AI応募者デモ: Meet の面接官の声 → STT → Groq → Gemini TTS → Anam アバター。

入力音声: ブラウザ(WebRTCクライアント)のマイク = 仮想デバイスA(Meetの出力を流し込む)
出力音声: ブラウザの再生先 = 仮想デバイスB(Meetのマイクにする)
出力映像: ブラウザ上のアバター表示をOBSでキャプチャ → OBS Virtual Camera
"""

import os
from pathlib import Path

from anam import PersonaConfig
from dotenv import load_dotenv
from loguru import logger
from pipecat_anam import AnamVideoService

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.groq.llm import GroqLLMService
from pipecat.services.google.tts import GeminiTTSService
from pipecat.transports.base_transport import BaseTransport, TransportParams

load_dotenv(override=True)

PERSONA = (Path(__file__).parent / "persona" / "candidate.md").read_text(encoding="utf-8")

transport_params = {
    "webrtc": lambda: TransportParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
        video_out_enabled=True,
        video_out_is_live=True,
        video_out_width=1280,
        video_out_height=720,
    ),
}


async def run_bot(transport: BaseTransport):
    stt = DeepgramSTTService(
        api_key=os.environ["DEEPGRAM_API_KEY"],
        settings=DeepgramSTTService.Settings(model="nova-3", language="ja"),
    )
    llm = GroqLLMService(
        api_key=os.environ["GROQ_API_KEY"],
        settings=GroqLLMService.Settings(
            model=os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
            system_instruction=PERSONA,
        ),
    )
    tts = GeminiTTSService(
        api_key=os.environ["GEMINI_API_KEY"],
        settings=GeminiTTSService.Settings(
            model=os.getenv("GEMINI_TTS_MODEL", "gemini-3.8-flash-tts"),
            voice=os.getenv("GEMINI_TTS_VOICE", "Charon"),
            prompt="落ち着いた自然な話し言葉の日本語で、面接を受ける応募者として丁寧に話す",
        ),
    )
    anam = AnamVideoService(
        api_key=os.environ["ANAM_API_KEY"],
        api_base_url="https://api.anam.ai",
        api_version="v1",
        persona_config=PersonaConfig(
            avatar_id=os.environ["ANAM_AVATAR_ID"],
            avatar_model="cara-4",
            enable_audio_passthrough=True,  # TTS音声でそのまま口を動かす
        ),
        enable_session_replay=False,
    )

    context = LLMContext([{"role": "user", "content": "面接が始まります。簡単に挨拶と自己紹介をしてください。"}])
    user_agg, assistant_agg = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer()),
    )

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            user_agg,
            llm,
            tts,
            anam,  # TTS音声 → 同期した音声+映像フレーム
            transport.output(),
            assistant_agg,
        ]
    )
    task = PipelineTask(
        pipeline,
        params=PipelineParams(enable_metrics=True),
    )

    @transport.event_handler("on_client_connected")
    async def on_connected(transport, client):
        logger.info("client connected")
        # 面接官が話し始める前に、こちらから挨拶する
        from pipecat.frames.frames import LLMRunFrame

        await task.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_disconnected")
    async def on_disconnected(transport, client):
        logger.info("client disconnected")
        await task.cancel()

    await PipelineRunner(handle_sigint=False).run(task)


async def bot(runner_args: RunnerArguments):
    transport = await create_transport(runner_args, transport_params)
    await run_bot(transport)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
