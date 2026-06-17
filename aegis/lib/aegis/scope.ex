defmodule Aegis.Scope do
  @moduledoc """
  Capability scope algebra — an independent Elixir re-derivation of the same
  host/port/path intersection the Python ScopeWarden uses in
  `governance/capability.py`, which is itself a clean-room port of
  `Hermes.Themis`. Aegis recomputes the intersection from first principles in a
  second runtime, so its attestation is a genuine cross-check, not an echo.

  The semantics below MUST stay byte-for-byte equivalent to the Python evaluator,
  or the attestation hashes will not match and the cross-framework agreement check
  fails loudly (which is the point — divergence is detectable):

    * hosts are globs; `*` matches exactly one DNS label (`[^.]+`).
    * paths are prefixes; `"/"` or `"*"` cover all; otherwise boundary-aware so a
      `/rest/products` grant matches `/rest/products` and `/rest/products/x` but
      NOT `/rest/products-evil`.
    * a child = parent ∩ restriction, field-wise; any empty field => `:empty_scope`
      (the deny-all sentinel — a caller cannot tunnel a no-op capability).
  """

  @enforce_keys [:hosts, :ports, :paths]
  defstruct hosts: [], ports: [], paths: ["/"]

  @type t :: %__MODULE__{hosts: [String.t()], ports: [integer()], paths: [String.t()]}

  @doc "Build a scope, coercing port strings to integers (mirrors ScopeSpec.of)."
  @spec new([String.t()], [integer() | String.t()], [String.t()]) :: t()
  def new(hosts, ports, paths \\ ["/"]) do
    %__MODULE__{hosts: hosts, ports: Enum.map(ports, &to_int/1), paths: paths}
  end

  defp to_int(p) when is_integer(p), do: p
  defp to_int(p) when is_binary(p), do: String.to_integer(String.trim(p))

  @doc """
  child = parent ∩ restriction. Returns `{:ok, scope}` or `{:error, :empty_scope}`
  when any field intersects to empty — identical to `issue_capability` raising
  `EmptyScopeError`.
  """
  @spec intersect(t(), t()) :: {:ok, t()} | {:error, :empty_scope}
  def intersect(%__MODULE__{} = parent, %__MODULE__{} = restriction) do
    hosts = Enum.filter(restriction.hosts, &host_match?(parent.hosts, &1))
    ports = Enum.filter(restriction.ports, &(&1 in parent.ports))
    paths = Enum.filter(restriction.paths, &path_match?(parent.paths, &1))

    if hosts == [] or ports == [] or paths == [] do
      {:error, :empty_scope}
    else
      {:ok, %__MODULE__{hosts: hosts, ports: ports, paths: paths}}
    end
  end

  @doc "Default-deny target check: host → port → path (mirrors check_capability)."
  @spec allows?(t(), String.t(), integer(), String.t()) :: boolean()
  def allows?(%__MODULE__{} = scope, host, port, path) do
    host_match?(scope.hosts, host) and port in scope.ports and path_match?(scope.paths, path)
  end

  @doc false
  def host_match?(globs, host), do: Enum.any?(globs, &glob_match?(&1, host))

  defp glob_match?(glob, host) do
    pattern = glob |> Regex.escape() |> String.replace("\\*", "[^.]+")

    case Regex.compile("^" <> pattern <> "$") do
      {:ok, re} -> Regex.match?(re, host)
      _ -> false
    end
  end

  @doc false
  def path_match?(prefixes, path), do: Enum.any?(prefixes, &one_path?(&1, path))

  defp one_path?(pref, _path) when pref in ["/", "*"], do: true

  defp one_path?(pref, path) do
    path == pref or String.starts_with?(path, String.trim_trailing(pref, "/") <> "/")
  end

  @doc """
  Canonical, order-independent string for the scope. Sorting each field makes the
  fingerprint stable regardless of the order the hosts/ports/paths were supplied.
  """
  @spec canonical(t()) :: String.t()
  def canonical(%__MODULE__{} = s) do
    hosts = s.hosts |> Enum.sort() |> Enum.join(",")
    ports = s.ports |> Enum.sort() |> Enum.map_join(",", &Integer.to_string/1)
    paths = s.paths |> Enum.sort() |> Enum.join(",")
    "hosts=#{hosts};ports=#{ports};paths=#{paths}"
  end

  @doc "SHA-256 hex of the canonical scope — the attestation fingerprint."
  @spec attestation_hash(t()) :: String.t()
  def attestation_hash(%__MODULE__{} = s) do
    :crypto.hash(:sha256, canonical(s)) |> Base.encode16(case: :lower)
  end
end
