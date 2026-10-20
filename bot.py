"""AI応募者デモ: Meet の面接官の声 → STT → Claude → Fish TTS → Anam アバター。

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
from pipecat.services.anthropic.llm import AnthropicLLMService
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.fish.tts import FishAudioTTSService
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
    llm = AnthropicLLMService(
        api_key=os.environ["ANTHROPIC_API_KEY"],
        settings=AnthropicLLMService.Settings(
            model=os.getenv("CLAUDE_MODEL", "claude-sonnet-4-5"),
            system_instruction=PERSONA,
        ),
    )
    tts = FishAudioTTSService(
        api_key=os.environ["FISH_API_KEY"],
        reference_id=os.environ["FISH_VOICE_ID"],
    )
    anam = AnamVideoService(
        api_key=os.environ["ANAM_API_KEY"],
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
