defmodule Aegis.MixProject do
  use Mix.Project

  # Aegis is a deliberately separate runtime: a real Elixir/OTP agent that joins
  # the same Band room as the Python swarm and independently re-derives the scope
  # algebra to attest the ScopeWarden's grants. It shares NO code with the Python
  # side — the only thing they share is the Band room. That is the cross-framework
  # claim, made literally true: two languages, two runtimes, one coordination layer.
  def project do
    [
      app: :aegis,
      version: "0.1.0",
      elixir: "~> 1.17",
      start_permanent: Mix.env() == :prod,
      escript: [main_module: Aegis.CLI],
      deps: deps()
    ]
  end

  def application do
    # OTP built-ins only — :inets/:ssl for the Band REST call, :crypto for the
    # attestation hash, :json (OTP 27+) for encoding. Zero hex dependencies, so
    # Aegis is provably independent of the Python band-sdk.
    [extra_applications: [:logger, :inets, :ssl, :crypto]]
  end

  defp deps, do: []
end
