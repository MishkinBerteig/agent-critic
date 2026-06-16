import httpx

from agent_critic.critic import critique

from .conftest import GEMMA, QWEN, make_client, make_request


async def test_critique_happy_path(config):
    client = make_client(
        '{"severity":"HIGH","severity_reason":"off-by-one","quality":"ADEQUATE","quality_reason":"ok"}'
    )
    env = await critique(client, config, make_request())
    assert env.severity == "HIGH"
    assert env.quality == "ADEQUATE"
    assert env.route == "coding"
    assert env.critic_model == GEMMA  # default critic
    assert env.spec == "agent-critic/0.1"


async def test_critique_excludes_generator(config):
    client = make_client('{"severity":"NONE","severity_reason":"-","quality":"GOOD","quality_reason":"-"}')
    # generator is gemma -> critic must be qwen
    env = await critique(client, config, make_request(generator_model=GEMMA))
    assert env.critic_model == QWEN
    assert client.seen[0]["model"] == QWEN


async def test_critique_network_failure_falls_back(config):
    def boom(request):
        raise httpx.ConnectError("down")

    client = httpx.AsyncClient(transport=httpx.MockTransport(boom))
    env = await critique(client, config, make_request())
    assert env.meta.get("fallback") is True
    assert env.severity == "OTHER"


async def test_critique_unparseable_falls_back(config):
    client = make_client("I think this looks fine honestly, no JSON for you")
    env = await critique(client, config, make_request(route="general"))
    assert env.meta.get("fallback") is True
