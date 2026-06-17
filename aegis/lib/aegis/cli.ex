defmodule Aegis.CLI do
  @moduledoc """
  Command-line entry point for the Aegis attestor (built as an escript).

      aegis attest --room <chat_id> \\
        --host localhost --port 3000 --parent-paths / \\
        --restrict-paths /rest/products \\
        [--expect-hash <sha256>] [--dry-run]

  Credentials come from the environment, never the command line:
      AEGIS_API_KEY   Aegis's Band agent API key (required unless --dry-run)
      BAND_REST_URL   Band REST base (default https://app.band.ai/)

  `--dry-run` computes and prints the attestation without touching the network —
  the offline proof that the Elixir re-derivation works, with no key or room.
  """

  alias Aegis.{Scope}

  @switches [
    room: :string,
    host: :string,
    port: :integer,
    parent_paths: :string,
    restrict_host: :string,
    restrict_port: :integer,
    restrict_paths: :string,
    expect_hash: :string,
    dry_run: :boolean
  ]

  def main(argv) do
    # escript stdout defaults to latin1, which mangles the attestation glyphs to
    # \x{...}; switch the group leader to unicode so the terminal echo is clean.
    :io.setopts(encoding: :unicode)
    {opts, rest, invalid} = OptionParser.parse(argv, strict: @switches)

    cond do
      invalid != [] ->
        die("unknown or malformed option(s): #{inspect(invalid)}")

      rest == ["check"] ->
        check()

      rest == ["attest"] ->
        attest(opts)

      true ->
        die(
          "usage: aegis attest --room <id> --restrict-paths <p1,p2> [--dry-run]  |  aegis check"
        )
    end
  end

  defp check do
    case Aegis.Band.check() do
      {:ok, status} ->
        IO.puts(
          "✓ Aegis (Elixir/#{System.otp_release()}) authenticated to Band at #{Aegis.Band.base_url()} (HTTP #{status}). Cross-framework wire OK."
        )

      {:error, :missing_api_key} ->
        die("AEGIS_API_KEY is not set — export Aegis's Band agent key")

      {:error, reason} ->
        die("Band auth check failed: #{inspect(reason)}")
    end
  end

  defp attest(opts) do
    host = Keyword.get(opts, :host, "localhost")
    port = Keyword.get(opts, :port, 3000)
    parent_paths = split(Keyword.get(opts, :parent_paths, "/"))

    parent = Scope.new([host], [port], parent_paths)

    restriction =
      Scope.new(
        [Keyword.get(opts, :restrict_host, host)],
        [Keyword.get(opts, :restrict_port, port)],
        split(Keyword.get(opts, :restrict_paths, Enum.join(parent_paths, ",")))
      )

    dry_run? = Keyword.get(opts, :dry_run, false)

    run_opts =
      [
        parent: parent,
        restriction: restriction,
        expected: Keyword.get(opts, :expect_hash),
        dry_run: dry_run?
      ]
      |> maybe_put_room(opts, dry_run?)

    case Aegis.run(run_opts) do
      {:ok, result} ->
        IO.puts(Aegis.message(result))
        IO.puts("  status=#{result.status}#{hash_line(result)}")
        unless dry_run?, do: IO.puts("  → posted to Band room #{Keyword.fetch!(run_opts, :room)}")
        # A scope disagreement or empty-scope deny is a governance FAILURE — exit
        # non-zero so a caller (or CI) treats it as the halt signal it is.
        if result.status in [:mismatch, :empty_scope], do: System.halt(2)

      {:error, :missing_api_key} ->
        die("AEGIS_API_KEY is not set — export Aegis's Band agent key, or use --dry-run")

      {:error, reason} ->
        die("Band post failed: #{inspect(reason)}")
    end
  end

  defp maybe_put_room(run_opts, _opts, true), do: run_opts

  defp maybe_put_room(run_opts, opts, false) do
    case Keyword.get(opts, :room) do
      room when is_binary(room) and room != "" -> Keyword.put(run_opts, :room, room)
      _ -> die("--room <chat_id> is required unless --dry-run")
    end
  end

  defp hash_line(%{hash: nil}), do: ""
  defp hash_line(%{hash: h}), do: " sha256=#{h}"

  defp split(csv), do: csv |> String.split(",", trim: true) |> Enum.map(&String.trim/1)

  defp die(msg) do
    IO.puts(:stderr, "aegis: #{msg}")
    System.halt(1)
  end
end
