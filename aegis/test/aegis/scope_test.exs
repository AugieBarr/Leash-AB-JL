defmodule Aegis.ScopeTest do
  use ExUnit.Case, async: true

  alias Aegis.Scope

  # These cases mirror governance/capability.py / tests/test_capability.py exactly.
  # If Aegis ever diverges from the Python evaluator, one of these goes red — which
  # is the whole point: the attestation is only meaningful if both runtimes agree.

  describe "intersect/2 (parent ∩ restriction)" do
    test "narrows paths while keeping host/port" do
      parent = Scope.new(["localhost"], [3000], ["/"])
      restriction = Scope.new(["localhost"], [3000], ["/rest/products"])
      assert {:ok, child} = Scope.intersect(parent, restriction)
      assert child.hosts == ["localhost"]
      assert child.ports == [3000]
      assert child.paths == ["/rest/products"]
    end

    test "a port outside the parent intersects to empty (deny-all)" do
      parent = Scope.new(["localhost"], [3000], ["/"])
      restriction = Scope.new(["localhost"], [9999], ["/"])
      assert {:error, :empty_scope} = Scope.intersect(parent, restriction)
    end

    test "a host outside the parent intersects to empty" do
      parent = Scope.new(["localhost"], [3000], ["/"])
      restriction = Scope.new(["evil.example.com"], [3000], ["/"])
      assert {:error, :empty_scope} = Scope.intersect(parent, restriction)
    end
  end

  describe "path_match?/2 boundary semantics" do
    test "a /rest/products grant covers the prefix and sub-paths but not look-alikes" do
      paths = ["/rest/products"]
      assert Scope.path_match?(paths, "/rest/products")
      assert Scope.path_match?(paths, "/rest/products/search")
      refute Scope.path_match?(paths, "/rest/products-evil")
      refute Scope.path_match?(paths, "/rest/productsX")
      refute Scope.path_match?(paths, "/ftp")
    end

    test "\"/\" and \"*\" cover all paths" do
      assert Scope.path_match?(["/"], "/anything/at/all")
      assert Scope.path_match?(["*"], "/anything/at/all")
    end
  end

  describe "host_match?/2 glob semantics (* = one DNS label)" do
    test "* matches a single label but not a dotted name" do
      assert Scope.host_match?(["*"], "localhost")
      refute Scope.host_match?(["*"], "a.b")
      assert Scope.host_match?(["*.example.com"], "api.example.com")
      refute Scope.host_match?(["*.example.com"], "deep.api.example.com")
    end
  end

  describe "allows?/4 default-deny evaluator" do
    test "permits in-scope, denies out-of-scope target" do
      {:ok, child} =
        Scope.intersect(
          Scope.new(["localhost"], [3000], ["/"]),
          Scope.new(["localhost"], [3000], ["/rest/products"])
        )

      assert Scope.allows?(child, "localhost", 3000, "/rest/products/search")
      refute Scope.allows?(child, "localhost", 3000, "/ftp")
      refute Scope.allows?(child, "localhost", 8080, "/rest/products")
    end
  end

  describe "attestation hash" do
    test "canonical is sorted and stable regardless of input order" do
      a = Scope.new(["localhost"], [3000], ["/b", "/a"])
      b = Scope.new(["localhost"], [3000], ["/a", "/b"])
      assert Scope.canonical(a) == Scope.canonical(b)
    end

    test "sha256 matches the independently-computed anchor (cross-tool agreement)" do
      child = Scope.new(["localhost"], [3000], ["/rest/products"])
      # printf '%s' "hosts=localhost;ports=3000;paths=/rest/products" | shasum -a 256
      assert Scope.attestation_hash(child) ==
               "f664c660319b95628bf9c92fd9458193c586338a2c607220ec3dcaf80e3af890"
    end
  end
end
