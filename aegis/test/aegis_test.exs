defmodule AegisTest do
  use ExUnit.Case, async: true

  alias Aegis.Scope

  defp grant do
    parent = Scope.new(["localhost"], [3000], ["/"])
    restriction = Scope.new(["localhost"], [3000], ["/rest/products"])
    {parent, restriction}
  end

  test "derive/3 attests when no expected hash is supplied" do
    {parent, restriction} = grant()
    result = Aegis.derive(parent, restriction)
    assert result.status == :attested
    assert result.hash == "f664c660319b95628bf9c92fd9458193c586338a2c607220ec3dcaf80e3af890"
    assert Aegis.event_type(result) == "tool_result"
    assert Aegis.message(result) =~ "GOVERNED"
  end

  test "derive/3 reports MATCH when the expected hash agrees" do
    {parent, restriction} = grant()
    expected = Scope.attestation_hash(Scope.new(["localhost"], [3000], ["/rest/products"]))
    result = Aegis.derive(parent, restriction, expected)
    assert result.status == :match
    assert Aegis.message(result) =~ "PASS"
  end

  test "derive/3 reports MISMATCH and escalates as an error event when hashes differ" do
    {parent, restriction} = grant()
    result = Aegis.derive(parent, restriction, "deadbeef")
    assert result.status == :mismatch
    assert Aegis.event_type(result) == "error"
    assert Aegis.message(result) =~ "HALT"
  end

  test "derive/3 denies an empty-scope grant and escalates as error" do
    parent = Scope.new(["localhost"], [3000], ["/"])
    restriction = Scope.new(["localhost"], [9999], ["/"])
    result = Aegis.derive(parent, restriction)
    assert result.status == :empty_scope
    assert Aegis.event_type(result) == "error"
    assert Aegis.message(result) =~ "DENY"
  end

  test "run/1 dry-run derives without touching the network" do
    {parent, restriction} = grant()
    assert {:ok, result} = Aegis.run(parent: parent, restriction: restriction, dry_run: true)
    assert result.status == :attested
  end
end
