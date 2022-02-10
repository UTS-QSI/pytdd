#pragma once
#include "stdafx.h"
#include "config.h"


namespace node {
	class Node;
}


namespace dict {

	struct unique_table_key {
		node_int order;
		node_int range;
		wcomplex* p_weights;
		const node::Node** p_nodes;
	};

	bool operator == (const unique_table_key & a, const unique_table_key & b);
	std::size_t hash_value(const unique_table_key& key_struct);




	typedef boost::unordered_map<unique_table_key, node::Node*> unique_table;
}

namespace node {

	//The node used in tdd.
	class Node
	{
	private:
		/*
			The precision for comparing two float numbers.
			It also decides the precision of weights stored in unique_table.
		*/
		static double m_EPS;

		// record the size of m_unique_table
		static int m_global_id;

		// The unique_table to store all the node instances used in tdd.
		static dict::unique_table m_unique_table;

		int m_id;

		//represent the order of this node (which tensor index it represent)
		node_int m_order;

		// the number of possible values of this index
		node_int m_range;

		wcomplex* mp_weights;

		// Note: terminal nodes are represented by nullptr in the successors.
		const Node** mp_successors;


	private:
		/// <summary>
		/// Count all the nodes starting from this node.
		/// </summary>
		/// <param name="total"> current total ids in p_id </param>
		/// <param name="p_id"> the memory to store all the ids (it is a borrowed pointer) </param>
		void node_search(std::vector<node_int> & id_ls) const;


	public:
		// Reset the dictionary caches.
		static void reset();

		// Get the EPS.
		static double EPS();

		// This function takes in the weight (tensor) and generates the integer key for unique_table.
		static int get_int_key(double weight);

		/// <summary>
		/// Constructor for new nodes (inner use only, otherwise refer to unique_table)
		/// Note that the dynanmically allocated p_out_weights and p_successors will be owned by this node.
		/// </summary>
		/// <param name="id"></param>
		/// <param name="order"></param>
		/// <param name="range"></param>
		/// <param name="p_out_weights">[ownership transfer]</param>
		/// <param name="p_successors">[ownership transfer]</param>
		Node(int id, node_int order, node_int range, wcomplex* p_weights, const Node** p_successors);

		~Node();

		node_int get_order() const;
		node_int get_range() const;
		const wcomplex* get_weights() const;
		const Node** get_successors() const;

		/// <summary>
		/// Count all the nodes starting from this one.
		/// </summary>
		/// <returns></returns>
		size_t get_size() const;

		/// <summary>
		/// Get the corresponding key structure of this node.
		/// </summary>
		/// <returns></returns>
		dict::unique_table_key get_key_struct() const;

		/// <summary>
		/// Calculate and return the Hash value of the node (can be nullptr).
		/// </summary>
		/// <param name="p_node"></param>
		/// <returns></returns>
		static std::size_t get_hash(Node* p_node);

		/// <summary>
		/// Return the required node. It is either from the unique table, or a newly created one.
		/// Note : The equality checking inside is conducted with the node.EPS tolerance.So feel free
		/// to pass in the raw weights from calculation.
		/// </summary>
		/// <param name="order">represent the order of this node(which tensor index it represent)</param>
		/// <param name="range">the count of possible value</param>
		/// <param name="weights">[onwership transfer] the weights of this node</param>
		/// <param name="successors">[onwership transfer] the successor nodes</param>
		/// <returns></returns>
		static Node* get_unique_node(node_int order, node_int range, wcomplex* p_weights, const Node** p_successors);
	};

	// The pointer of the terminal node (nullptr).
	Node* const TERMINAL_NODE = nullptr;
}