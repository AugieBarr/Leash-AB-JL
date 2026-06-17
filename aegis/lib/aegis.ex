defmodule Aegis do
  @moduledoc """
  Aegis — the cross-framework scope attestor.

  When the Python ScopeWarden narrows the engagement capability for a specialist
  (parent ∩ restriction), Aegis independently recomputes that intersection in
  Elixir and posts the verdict into the same Band room as a `tool_result` event
  (or an `error` event on disagreement / deny). Two runtimes, no shared code, one
  coordination layer — the governance grant is cross-checked by a second framework
  before any specialist acts on it.

  `derive/3` is pure (and fully testable offline); `run/1` derives and posts.
  """

  alias Aegis.{Band, Scope}

  @type status :: :attested | :match | :mismatch | :empty_scope

  defmodule Result do
    @moduledoc false
    @enforce_keys [:status, :detail]
    defstruct [:status, :child, :hash, :expected, :detail]
  end

  @doc """
  Pure attestation. `expected` is the hash the Python side derived for the same
  grant; when supplied, Aegis reports `:match`/`:mismatch` instead of a bare
  `:attested`, turning agreement into a real comparison rather than a claim.
  """
  @spec derive(Scope.t(), Scope.t(), String.t() | nil) :: Result.t()
  def derive(%Scope{} = parent, %Scope{} = restriction, expected \\ nil) do
    case Scope.intersect(parent, restriction) do
      {:ok, child} ->
        hash = Scope.attestation_hash(child)

        status =
          cond do
            is_nil(expected) -> :attested
            expected == hash -> :match
            true -> :mismatch
          end

        %Result{
          status: status,
          child: child,
          hash: hash,
          expected: expected,
          detail: detail(status, child, hash, expected)
        }

      {:error, :empty_scope} ->
        %Result{
          status: :empty_scope,
          detail:
            "restriction intersects the parent capability to an EMPTY (deny-all) scope — grant rejected"
        }
    end
  end

  @doc "The human-readable line Aegis posts into the Band room for a result."
  @spec message(Result.t()) :: String.t()
  def message(%Result{status: :attested, child: c, hash: h}) do
    "🛡️ AEGIS (Elixir/OTP) attests the ScopeWarden grant — scope #{Scope.canonical(c)}, sha256 #{short(h)}. Independent cross-framework re-derivation: GOVERNED."
  end

  def message(%Result{status: :match, child: c, hash: h}) do
    "🛡️ AEGIS (Elixir) ✓ ATTESTED — my independent re-derivation MATCHES the Python ScopeWarden for #{Scope.canonical(c)} (sha256 #{short(h)}). Cross-framework governance check: PASS."
  end

  def message(%Result{status: :mismatch, hash: h, expected: e}) do
    "🛡️ AEGIS (Elixir) ✗ SCOPE MISMATCH — my re-derivation #{short(h)} ≠ ScopeWarden's #{short(e)}. The two frameworks disagree on the grant. Recommend HALT."
  end

  def message(%Result{status: :empty_scope}) do
    "🛡️ AEGIS (Elixir) ✗ DENY — the restriction intersects to an empty scope. Grant rejected before any specialist can act."
  end

  @doc "Band event type for a result — disagreement/deny escalate as `error`."
  @spec event_type(Result.t()) :: String.t()
  def event_type(%Result{status: s}) when s in [:attested, :match], do: "tool_result"
  def event_type(%Result{status: s}) when s in [:mismatch, :empty_scope], do: "error"

  @doc """
  Derive and post the attestation into the Band room. Returns the `Result` on a
  successful post, or `{:error, reason}` if the Band call fails (missing key,
  transport, non-2xx). `dry_run: true` skips the network and just returns the
  result — used by the offline check and tests.
  """
  @spec run(keyword()) :: {:ok, Result.t()} | {:error, term()}
  def run(opts) do
    parent = Keyword.fetch!(opts, :parent)
    restriction = Keyword.fetch!(opts, :restriction)
    result = derive(parent, restriction, Keyword.get(opts, :expected))

    cond do
      Keyword.get(opts, :dry_run, false) ->
        {:ok, result}

      true ->
        room = Keyword.fetch!(opts, :room)

        metadata = %{
          "agent" => "aegis",
          "framework" => "elixir/#{System.otp_release()}",
          "scope" => (result.child && Scope.canonical(result.child)) || "(empty)",
          "sha256" => result.hash || "",
          "status" => Atom.to_string(result.status)
        }

        case Band.post_event(room, event_type(result), message(result), metadata) do
          {:ok, _status} -> {:ok, result}
          {:error, reason} -> {:error, reason}
        end
    end
  end

  defp detail(:attested, child, hash, _),
    do: "attested #{Scope.canonical(child)} (sha256 #{hash})"

  defp detail(:match, child, hash, _),
    do: "MATCH — #{Scope.canonical(child)} agrees with ScopeWarden (sha256 #{hash})"

  defp detail(:mismatch, _child, hash, expected),
    do: "MISMATCH — derived #{hash}, expected #{expected}"

  defp short(nil), do: "(none)"
  defp short(hash), do: String.slice(hash, 0, 12) <> "…"
end
