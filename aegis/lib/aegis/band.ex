defmodule Aegis.Band do
  @moduledoc """
  Minimal Band (thenvoi) REST client built on OTP built-ins only — `:httpc`,
  `:ssl`, `:json`. Zero hex dependencies on purpose: Aegis shares no SDK with the
  Python swarm, so the only thing connecting the two runtimes is the Band room.

  Wire contract (read from the thenvoi_rest SDK, `agent_api_messages` /
  `agent_api_events`):

      POST {base}/api/v1/agent/chats/{chat_id}/events     — structured event (no @mention)
      POST {base}/api/v1/agent/chats/{chat_id}/messages   — text message (needs @mention)
      auth:  X-API-Key: <agent api key>
      body:  {"event":  {"content","message_type","metadata"}}
             {"message":{"content","mentions":[{"id","handle","name"}]}}

  The agent must already be a participant in the room (added via the seeder or a
  recruit call) for the post to be accepted.
  """
  require Logger

  @default_base "https://app.band.ai/"
  @event_types ~w(tool_call tool_result thought error task)

  @doc "Resolved Band REST base URL (`BAND_REST_URL` overrides the app.band.ai default)."
  def base_url do
    System.get_env("BAND_REST_URL", @default_base) |> String.trim_trailing("/")
  end

  @doc "Aegis's Band agent API key, from `AEGIS_API_KEY`. Never logged."
  @spec api_key() :: {:ok, String.t()} | {:error, :missing_api_key}
  def api_key do
    case System.get_env("AEGIS_API_KEY") do
      key when is_binary(key) and key != "" -> {:ok, key}
      _ -> {:error, :missing_api_key}
    end
  end

  @doc """
  Post a structured governance event into a room. `message_type` must be one of
  #{inspect(@event_types)}. Events do not require an @mention.
  """
  @spec post_event(String.t(), String.t(), String.t(), map()) ::
          {:ok, integer()} | {:error, term()}
  def post_event(chat_id, message_type, content, metadata \\ %{})
      when message_type in @event_types do
    body = %{
      "event" => %{
        "content" => content,
        "message_type" => message_type,
        "metadata" => metadata
      }
    }

    request("api/v1/agent/chats/#{chat_id}/events", body)
  end

  @doc """
  Post a text message into a room. `mentions` is a list of
  `%{"id" => _, "handle" => _, "name" => _}`; Band requires at least one for
  routing.
  """
  @spec post_message(String.t(), String.t(), [map()]) :: {:ok, integer()} | {:error, term()}
  def post_message(chat_id, content, mentions) when is_list(mentions) do
    body = %{"message" => %{"content" => content, "mentions" => mentions}}
    request("api/v1/agent/chats/#{chat_id}/messages", body)
  end

  @doc """
  Read-only auth probe: GET the agent's chat list. A 2xx proves this Elixir
  runtime authenticates against Band with `AEGIS_API_KEY` — the cross-framework
  wire works — with no side effect on any room.
  """
  @spec check() :: {:ok, integer()} | {:error, term()}
  def check do
    with {:ok, key} <- api_key() do
      {:ok, _} = :application.ensure_all_started(:inets)
      {:ok, _} = :application.ensure_all_started(:ssl)

      url = String.to_charlist("#{base_url()}/api/v1/agent/chats")
      headers = [{~c"x-api-key", String.to_charlist(key)}]
      http_opts = [timeout: 15_000, connect_timeout: 10_000]

      case :httpc.request(:get, {url, headers}, http_opts, body_format: :binary) do
        {:ok, {{_v, status, _r}, _h, _resp}} when status in 200..299 -> {:ok, status}
        {:ok, {{_v, status, _r}, _h, resp}} -> {:error, {:http_status, status, truncate(resp)}}
        {:error, reason} -> {:error, {:transport, reason}}
      end
    end
  end

  defp request(path, body) do
    with {:ok, key} <- api_key() do
      {:ok, _} = :application.ensure_all_started(:inets)
      {:ok, _} = :application.ensure_all_started(:ssl)

      url = String.to_charlist("#{base_url()}/#{path}")
      payload = body |> :json.encode() |> IO.iodata_to_binary()
      headers = [{~c"x-api-key", String.to_charlist(key)}]
      http_opts = [timeout: 15_000, connect_timeout: 10_000]
      opts = [body_format: :binary]

      case :httpc.request(:post, {url, headers, ~c"application/json", payload}, http_opts, opts) do
        {:ok, {{_v, status, _r}, _h, _resp}} when status in 200..299 ->
          {:ok, status}

        {:ok, {{_v, status, _r}, _h, resp}} ->
          {:error, {:http_status, status, truncate(resp)}}

        {:error, reason} ->
          {:error, {:transport, reason}}
      end
    end
  end

  defp truncate(bin) when is_binary(bin), do: String.slice(bin, 0, 400)
  defp truncate(other), do: inspect(other)
end
