#pragma once
#include "stdafx.h"
#include "cache.hpp"
#include "succ_ls.hpp"

namespace node {


	// The node used in tdd.
	template <typename W>
	class Node {
	private:

		// The unique_table to store all the node instances used in tdd.
		static cache::unique_table<W>* mp_unique_table;
		static std::shared_mutex unique_table_m;

		//represent the order of this node (which tensor index it represent)
		int m_order;

		/* The weight and node of the successors
		*  Note: terminal nodes are represented by nullptr in the successors.
		*/
		succ_ls<W> m_successors;

	private:


		/// <summary>
		/// Count all the nodes starting from this node.
		/// </summary>
		/// <param name="id_ls"> the vector to store all the ids</param>
		void node_search(boost::unordered_set<const Node<W>*>& node_ls) const {
			// check whether it is in node_ls already, and insert in
			auto&& insert_res = node_ls.insert(this);

			if (insert_res.second) {
				// it is not counted yet in this case
				for (const auto& succ : m_successors) {
					if (!succ.isterminal()) {
						succ.node->node_search(node_ls);
					}
				}
			}
		}


		/// <summary>
		/// insert this node and all sub nodes to the new unique table
		/// </summary>
		/// <param name="p_unique_table"></param>
		/// <param name="inserted">record whether the node of particular id has been inserted</param>
		const Node<W>* unique_table_insert(cache::unique_table<W>* p_unique_table, 
			boost::unordered_map<const Node<W>*, const Node<W>*>& inserted_nodes) const {

			// find in the cache
			auto&& p_find_res = inserted_nodes.find(this);
			if (p_find_res != inserted_nodes.end()) {
				return p_find_res->second;
			}

			succ_ls<W> new_successors(m_successors.size());

			// first update the subnodes
			for (int i = 0; i < m_successors.size(); i++) {
				if (m_successors[i].node) {
					new_successors[i] = weightednode<W>(std::move(m_successors[i].weight),
						m_successors[i].node->unique_table_insert(p_unique_table, inserted_nodes));
				}
				else {
					new_successors[i] = weightednode<W>(std::move(m_successors[i]));
				}
			}

			const Node<W>* p_res;
			auto&& key = cache::unique_table_key<W>(m_order, new_successors);
			p_res = new Node{ m_order, std::move(new_successors) };
			(*p_unique_table)[key] = p_res;
			inserted_nodes[this] = p_res;
			return p_res;
		}


	public:


		Node(int order, succ_ls<W>&& successors) :m_order(order), m_successors(std::move(successors)) {}

		Node(Node<W>&& _node) {
			*this = std::move(_node);
		}

		/// <summary>
		/// clear the unique_table, except the designated nodes and its successors.
		/// id is rearranged.
		/// </summary>
		/// <param name="remained_nodes"></param>
		/// <returns> the corresponding new nodes of those in remained_nodes </returns>
		static std::vector<const Node<W>*> reset(const std::vector<const Node<W>*>& remained_nodes = {}) {

			auto new_unique_table = new cache::unique_table<W>{};
			boost::unordered_map<const Node<W>*, const Node<W>*> inserted_nodes{};
			std::vector<const Node<W>*> res_nodes{ remained_nodes.size() };

			for (int i = 0; i < remained_nodes.size(); i++) {
				res_nodes[i] = remained_nodes[i]->unique_table_insert(new_unique_table, inserted_nodes);
			}

			for (auto&& i : *mp_unique_table) {
				delete i.second;
			}

			delete mp_unique_table;
			mp_unique_table = new_unique_table;
			return res_nodes;
		}

		/// <summary>
		/// Note: when the successors passed in is a left value, it will be copied first.
		/// When the equality checking inside is conducted with the node.EPS tolerance.So feel free
		/// to pass in the raw weights from calculation.
		/// </summary>
		/// <param name="order"></param>
		/// <param name="successors"></param>
		/// <returns></returns>
		template <bool PL>
		static const Node<W>* get_unique_node(int order, const succ_ls<W>& successors) {
			auto&& key = cache::unique_table_key<W>(order, successors);

			//>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
			if constexpr (PL) {
				unique_table_m.lock();
			}
			auto&& p_find_res = mp_unique_table->find(key);

			if (p_find_res != mp_unique_table->end()) {
				if constexpr (PL) {
					unique_table_m.unlock();
				}
				//<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<
				return p_find_res->second;
			}

			node::Node<W>* p_node = new node::Node<W>(order, succ_ls<W>(successors));

			(*mp_unique_table)[key] = p_node;
			if constexpr (PL) {
				unique_table_m.unlock();
			}
			//<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<

			return p_node;
		}

		/// <summary>
		/// Note: when the successors passed in is a right value, it will be transfered to the new node.
		/// When the equality checking inside is conducted with the node.EPS tolerance.So feel free
		/// to pass in the raw weights from calculation.
		/// </summary>
		/// <param name="order"></param>
		/// <param name="successors"></param>
		/// <returns></returns>
		template <bool PL>
		static const Node<W>* get_unique_node(int order, succ_ls<W>&& successors) {
			auto&& key = cache::unique_table_key<W>(order, successors);

			//>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
			if constexpr (PL) {
				unique_table_m.lock();
			}
			auto&& p_find_res = mp_unique_table->find(key);

			if (p_find_res != mp_unique_table->end()) {
				if constexpr (PL) {
					unique_table_m.unlock();
				}
				//<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<
				return p_find_res->second;
			}

			node::Node<W>* p_node = new node::Node<W>(order, std::move(successors));

			(*mp_unique_table)[key] = p_node;
			if constexpr (PL) {
				unique_table_m.unlock();
			}
			//<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<

			return p_node;
		}

		inline int get_order() const {
			return m_order;
		}

		inline int get_range() const {
			return m_successors.size();
		}

		void print() const {
			for (int i = 0; i < m_order; i++) {
				std::cout << "-";
			}
			std::cout << "=======" << std::endl;
			for (int i = 0; i < m_order; i++) {
				std::cout << " ";
			}
			std::cout << "|node: " << this << std::endl;

			for (int i = 0; i < m_order; i++) {
				std::cout << " ";
			}
			std::cout << "|order: " << m_order << std::endl;

			for (int i = 0; i < m_order; i++) {
				std::cout << " ";
			}
			std::cout << "|successors: " << std::endl;

			for (int j = 0; j < m_successors.size(); j++) {
				for (int i = 0; i < m_order; i++) {
					std::cout << " ";
				}
				std::cout << "|  " << j << " " << "weight: " << m_successors[j].weight << std::endl;
				for (int i = 0; i < m_order; i++) {
					std::cout << " ";
				}
				std::cout << "|  " << j << " " << "node: " << m_successors[j].node << std::endl;
			}

			for (const auto& succ : m_successors) {
				if (succ.node != nullptr) {
					succ.node->print();
				}
			}
		}

		inline const succ_ls<W>& get_successors() const {
			return m_successors;
		}

		/// <summary>
		/// Count all the nodes starting from this one.
		/// </summary>
		/// <returns></returns>
		inline int get_size() const {
			auto&& node_ls = boost::unordered_set<const Node<W>*>{};
			node_search(node_ls);
			// the terminal node is counted
			return node_ls.size() + 1;
		}
	};
}